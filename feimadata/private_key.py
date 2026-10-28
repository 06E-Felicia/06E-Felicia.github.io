"""Local MCP credential storage, outside the project and web root."""
import getpass
import os
from pathlib import Path
import stat
import sys

KEY_DIR = (Path.home() / 'Library/Application Support/Feimadat' if sys.platform == 'darwin'
           else Path.home() / '.config/Feimadat')
KEY_FILE = KEY_DIR / 'mcp-key'
ENV_NAME = 'VARIFLIGHT_MCP_KEY'


class KeyErrorSafe(RuntimeError):
    pass


def validate_key(value):
    value = value.strip()
    if value.lower().startswith('bearer '):
        value = value[7:].strip()
    if not 8 <= len(value) <= 8192 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise KeyErrorSafe('密钥格式不正确，请只复制控制台中的 MCP Key，不要复制整个配置 JSON')
    if value.startswith(('{', '[')):
        raise KeyErrorSafe('请只粘贴 MCP Key，不要粘贴整个配置 JSON')
    return value


def load_key():
    if os.environ.get(ENV_NAME):
        return validate_key(os.environ[ENV_NAME])
    try:
        fd = os.open(KEY_FILE, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'r', encoding='utf-8') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise KeyErrorSafe('本机密钥文件权限不安全，请重新运行配置启动器')
            return validate_key(source.read(8193))
    except KeyErrorSafe:
        raise
    except FileNotFoundError:
        raise KeyErrorSafe('尚未配置 MCP Key，请运行 development/launchers/配置飞常准.command') from None
    except Exception:
        raise KeyErrorSafe('本机 MCP Key 无法读取，请重新运行配置启动器') from None


def save_key(value):
    value = validate_key(value)
    if KEY_DIR.is_symlink():
        raise KeyErrorSafe('私有配置目录不可为符号链接')
    KEY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    KEY_DIR.chmod(0o700)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        output.write(value)


def main():
    print('飞常准 MCP Key 本机配置（不是 FR24 登录配置）')
    print('密钥只保存在当前用户的私有配置目录，不写入项目、网页或 Git。')
    print('粘贴时不显示字符，这是正常现象；请勿把密钥发到聊天。')
    first = getpass.getpass('粘贴 MCP Key，然后按回车：')
    save_key(first)
    print('MCP Key 已安全保存。请告诉助手“飞常准密钥已配置”。')
    print('此操作仅保存密钥，没有调用机场接口，也没有启动自动采集。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('\n已取消。')
        raise SystemExit(1)
    except KeyErrorSafe as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('未能保存密钥，请检查私有目录权限后重试。', file=sys.stderr)
        raise SystemExit(1)
