"""Canal privado efêmero para state e plan do Terraform (§10.2): disco de RAM cifrado, apagado no fim.

macOS (o runner):  hdiutil attach -nomount ram://N  ->  confere em `hdiutil info -plist` que o dispositivo é
                   uma imagem ram:// criada agora  ->  diskutil apfs createContainer  ->  addVolume APFS com
                   senha aleatória lida da entrada padrão (-stdinpassphrase; volume cifrado)  ->  uso  ->
                   apaga os arquivos  ->  hdiutil detach -force (a RAM some e a senha, que só existiu em memória,
                   vai junto: apagamento criptográfico).
Linux (a VM):      diretório 0700 num tmpfs (/dev/shm) e recusa se houver swap ativa (página de RAM iria para o
                   disco em claro); o supervisor não precisa de state, só do manifesto.
Teste:             SimulatedBackend (pasta em $BO_TMP): simulated=True, e o runner de nuvem o recusa.

Toda operação de disco só acontece sobre o dispositivo conferido como ram://; nada aqui formata outro disco.
"""

from __future__ import annotations

import os
import plistlib
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from .common import SafetyError, bo_tmp

SECTOR = 512


class EphemeralError(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "EPHEMERAL")


def _run(argv, inp: bytes | None = None, check=True) -> bytes:
    r = subprocess.run(argv, input=inp, capture_output=True, timeout=120)
    if check and r.returncode != 0:
        raise EphemeralError(f"{argv[0]} {argv[1] if len(argv) > 1 else ''} falhou (código {r.returncode})")
    return r.stdout


class SimulatedBackend:
    """Pasta comum em $BO_TMP. Só para testes e simulação: não é RAM nem cifrada."""
    simulated = True
    ram = False
    encrypted = False
    name = "simulated"

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else bo_tmp() / "ephemeral_sim"
        self.path: Path | None = None

    def open(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / ("eph-" + secrets.token_hex(6))
        self.path.mkdir(mode=0o700)
        return self.path

    def close(self) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path)
        self.path = None


class MacRamBackend:
    """Disco de RAM com volume APFS cifrado (senha aleatória só em memória)."""
    simulated = False
    ram = True
    encrypted = True
    name = "macos-ram-apfs-encrypted"

    def __init__(self, size_mb: int = 1536, volname: str | None = None):
        self.size_mb = size_mb
        self.volname = volname or ("boeph" + secrets.token_hex(3))
        self.dev: str | None = None
        self.path: Path | None = None

    def _ram_devices(self) -> set[str]:
        info = plistlib.loads(_run(["hdiutil", "info", "-plist"]))
        devs = set()
        for img in info.get("images", []):
            if str(img.get("image-path", "")).startswith("ram://"):
                for ent in img.get("system-entities", []):
                    if ent.get("dev-entry"):
                        devs.add(ent["dev-entry"])
        return devs

    def open(self) -> Path:
        sectors = self.size_mb * 1024 * 1024 // SECTOR
        before = self._ram_devices()
        dev = _run(["hdiutil", "attach", "-nomount", f"ram://{sectors}"]).decode().strip().split()[0]
        if not dev.startswith("/dev/disk") or dev not in self._ram_devices() or dev in before:
            raise EphemeralError("dispositivo devolvido pelo hdiutil não é a imagem ram:// recém-criada; nada feito")
        self.dev = dev
        try:
            _run(["diskutil", "apfs", "createContainer", dev])
            container = self._container_of(dev)
            pw = secrets.token_urlsafe(32).encode()
            _run(["diskutil", "apfs", "addVolume", container, "APFS", self.volname, "-stdinpassphrase"], inp=pw + b"\n")
            del pw
            mp = self._mountpoint(container)
            self.path = Path(mp) / ("eph-" + secrets.token_hex(6))
            self.path.mkdir(mode=0o700)
            if not self._is_encrypted(container):
                raise EphemeralError("volume do disco de RAM não está cifrado")
        except Exception:
            self.close()
            raise
        return self.path

    def _apfs(self) -> dict:
        return plistlib.loads(_run(["diskutil", "apfs", "list", "-plist"]))

    def _container_of(self, dev: str) -> str:
        devid = dev.replace("/dev/", "")
        for c in self._apfs().get("Containers", []):
            for st in c.get("PhysicalStores", []):
                sid = st.get("DeviceIdentifier", "")
                if sid == devid or sid.startswith(devid + "s"):
                    return c["ContainerReference"]
        raise EphemeralError("contêiner APFS do disco de RAM não encontrado")

    def _volume(self, container: str) -> dict:
        for c in self._apfs().get("Containers", []):
            if c.get("ContainerReference") == container:
                for v in c.get("Volumes", []):
                    if v.get("Name") == self.volname:
                        return v
        raise EphemeralError("volume do disco de RAM não encontrado")

    def _mountpoint(self, container: str) -> str:
        vol = self._volume(container)
        info = plistlib.loads(_run(["diskutil", "info", "-plist", vol["DeviceIdentifier"]]))
        mp = info.get("MountPoint")
        if not mp:
            raise EphemeralError("volume cifrado do disco de RAM não montou")
        return mp

    def _is_encrypted(self, container: str) -> bool:
        v = self._volume(container)
        return bool(v.get("Encryption") or v.get("FileVault"))

    def close(self) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        if self.dev:
            if self.dev not in self._ram_devices():
                raise EphemeralError("recusado: dispositivo a desmontar não é mais a imagem ram:// do canal")
            _run(["hdiutil", "detach", self.dev, "-force"], check=False)
        self.dev, self.path = None, None


class LinuxTmpfsBackend:
    """tmpfs (RAM) sem swap ativa. A cifra é a ausência de qualquer cópia em disco; com swap, recusa."""
    simulated = False
    ram = True
    encrypted = True
    name = "linux-tmpfs-noswap"

    def __init__(self, base: str = "/dev/shm"):
        self.base = Path(base)
        self.path: Path | None = None

    def open(self) -> Path:
        mounts = Path("/proc/mounts").read_text().splitlines()
        if not any(ln.split()[1] == str(self.base) and ln.split()[2] in ("tmpfs", "ramfs") for ln in mounts):
            raise EphemeralError(f"{self.base} não é tmpfs/ramfs")
        swaps = [ln for ln in Path("/proc/swaps").read_text().splitlines()[1:] if ln.strip()]
        if swaps:
            raise EphemeralError("swap ativa: página do state poderia ir para o disco; recusado")
        self.path = self.base / ("bo-eph-" + secrets.token_hex(6))
        self.path.mkdir(mode=0o700)
        return self.path

    def close(self) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        self.path = None


def default_backend():
    if sys.platform == "darwin":
        return MacRamBackend()
    if sys.platform.startswith("linux"):
        return LinuxTmpfsBackend()
    raise EphemeralError(f"plataforma sem canal efêmero: {sys.platform}")


class EphemeralChannel:
    """Contexto do canal: TF_DATA_DIR, state local e plano ficam dentro; ao sair, tudo apagado.

    env() devolve as variáveis que mantêm o Terraform no canal: TF_DATA_DIR, TF_CLI_ARGS_init com o caminho do
    state local, TF_CLI_ARGS_plan/apply/destroy com -state, e TF_LOG desligado (log pode ter segredo)."""

    def __init__(self, backend=None):
        self.backend = backend or default_backend()
        self.path: Path | None = None

    def __enter__(self):
        self.path = self.backend.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        self.backend.close()
        self.path = None

    @property
    def live_ok(self) -> bool:
        return bool(self.backend.ram and self.backend.encrypted and not self.backend.simulated)

    def state_path(self) -> Path:
        return self.path / "terraform.tfstate"

    def plan_path(self) -> Path:
        return self.path / "plan.tfplan"

    def workdir(self) -> Path:
        d = self.path / "work"
        d.mkdir(mode=0o700, exist_ok=True)
        return d

    def env(self) -> dict:
        if not self.path:
            raise EphemeralError("canal efêmero fechado")
        st = str(self.state_path())
        return {
            "TF_DATA_DIR": str(self.path / ".terraform"),
            "TF_CLI_ARGS_init": f"-backend-config=path={st}",
            "TF_LOG": "",
            "TF_LOG_PATH": "",
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TMPDIR": str(self.path),
        }

    def contains(self, p: Path) -> bool:
        if not self.path:
            return False
        r = self.path.resolve()
        q = Path(p).resolve()
        return q == r or r in q.parents


def assert_terraform_env_clean(env: dict) -> list[str]:
    """Variáveis que tirariam state, plano ou log do canal efêmero (ou mudariam a conta sem o identity_guard)."""
    probs = []
    if env.get("TF_LOG") or env.get("TF_LOG_CORE") or env.get("TF_LOG_PROVIDER"):
        probs.append("TF_LOG ligado (log do Terraform pode conter valores sensíveis)")
    if env.get("TF_LOG_PATH"):
        probs.append("TF_LOG_PATH definido fora do canal")
    if env.get("TF_WORKSPACE"):
        probs.append("TF_WORKSPACE definido (state de outro workspace)")
    for k in env:
        if k.startswith("TF_CLI_ARGS") and "-state" in env[k] and "terraform.tfstate" not in env[k]:
            probs.append(f"{k} aponta state para fora do canal")
    return probs


if __name__ == "__main__":  # pragma: no cover - verificação manual: abre e fecha um canal real pequeno
    ch = EphemeralChannel(MacRamBackend(size_mb=64) if sys.platform == "darwin" else None)
    with ch:
        (ch.path / "teste").write_text("x")
        print(f"canal {ch.backend.name}: ram={ch.backend.ram} cifrado={ch.backend.encrypted} -> ok")
    print("canal fechado")
    sys.exit(0)
