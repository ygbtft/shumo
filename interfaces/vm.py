"""把运行包复制到 Parallels Windows VM，并执行配置检查。"""
import argparse
import base64
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
PRL = '/Applications/Parallels Desktop.app/Contents/MacOS/prlctl'


def quote(value):
    # PowerShell 单引号字符串中的单引号，用两个单引号表示。
    return "'" + str(value).replace("'", "''") + "'"


def guest(script, vm):
    # EncodedCommand 接收 UTF-16LE，避免中文路径经过两层命令行时编码改变。
    body = "$ErrorActionPreference='Stop'\n$ProgressPreference='SilentlyContinue'\n" + script
    encoded = base64.b64encode(body.encode('utf-16le')).decode('ascii')
    command = [PRL, 'exec', vm, 'powershell.exe', '-NoProfile', '-EncodedCommand', encoded]
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'deploy', 'check-config'))
    parser.add_argument('--vm', default='Windows 11')
    parser.add_argument('--destination', default=r'C:\BDelivery')
    parser.add_argument('--python', default=r'C:\Python314-arm64\python.exe')
    parser.add_argument('--archive', type=Path, default=ROOT / 'dist/delivery.zip')
    parser.add_argument('--problem', type=int, choices=(3, 4), default=3)
    args = parser.parse_args()
    destination = quote(args.destination)
    python = quote(args.python)

    if args.action == 'status':
        script = 'Get-Process -Name jammers-simulator -ErrorAction SilentlyContinue | Select-Object Name,Id,SessionId\n'
        script += f'& {python} --version\nexit $LASTEXITCODE'
    elif args.action == 'deploy':
        # VM 只共享 Downloads；先把本次 zip 放入独立的传输目录。
        transfer = Path.home() / 'Downloads' / ('BDelivery-' + uuid.uuid4().hex[:10])
        transfer.mkdir()
        shutil.copy2(args.archive, transfer / 'delivery.zip')
        source = quote('\\\\Mac\\Home\\Downloads\\' + transfer.name + '\\delivery.zip')
        script = f'Expand-Archive -LiteralPath {source} -DestinationPath {destination}\n'
        script += f"& {python} -B ({destination}+'\\tools\\verify_bundle.py')\nexit $LASTEXITCODE"
    else:
        script = f"& {python} -B ({destination}+'\\interfaces\\official.py') --problem {args.problem} --check-config\n"
        script += 'exit $LASTEXITCODE'
    guest(script, args.vm)


if __name__ == '__main__':
    main()
