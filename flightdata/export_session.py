"""Human sign-in in an isolated window; export only scoped FR24 state."""
import argparse
import sys

try:
    from . import fr24_session as session
    from . import scraper
except ImportError:
    import fr24_session as session
    import scraper


def main():
    parser=argparse.ArgumentParser(description='本机人工登录 FR24，保存私有 Actions 会话')
    parser.add_argument('--channel',default='chrome',help='已安装的浏览器 channel，默认 chrome')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright
    print('将打开项目专用浏览器，不读取普通 Chrome 的个人资料。')
    print('请在窗口中自行登录 FR24；密码、验证码均由你本人输入。')
    print('仅会导出 FR24 会话，不导出其他站点或 Cloudflare 通行凭据。',flush=True)
    with sync_playwright() as pw:
        try:
            prior=session.load_state()
        except session.SessionError:
            prior=None
        browser=pw.chromium.launch(channel=args.channel,headless=False)
        try:
            options={'locale':'en-US','timezone_id':'Asia/Shanghai','viewport':{'width':1280,'height':900}}
            if prior:
                options['storage_state']=prior
            try:
                context=browser.new_context(**options)
            except Exception:
                raise session.SessionError('专用浏览器无法恢复旧会话，请先移走 .auth 中的旧会话后重新登录') from None
            page=context.new_page()
            page.goto('https://www.flightradar24.com/data/airports/szx/arrivals',wait_until='domcontentloaded',timeout=75000)
            input('\n完成登录后，在此按回车核验并保存（或告诉助手“专用窗口已登录”）…')
            cfg=scraper.load_config();cfg=dict(cfg,max_retries=1)
            data=scraper.fetch_board(page,'arrivals',cfg['airports'][0],cfg,False)
            hours=session.assert_24h(data)
            state_file,secret_file=session.save_private_state(context.storage_state())
            print(f'当前专用浏览器已验证 {hours:g} 小时查看范围。')
            print(f'本地私有会话：{state_file}')
            print(f'GitHub Secret 导入文件：{secret_file}')
            print(f'Secret 名称：{session.SECRET_NAME}')
            print('文件权限仅当前用户可读写，已被 Git 忽略；内容不会打印到终端。')
            print('请勿将这两个文件上传到仓库、聊天、截图或 Actions 附件。')
            print('Base64 不是加密；只能将导入文件的内容保存到 Actions Secret。')
            return 0
        finally:
            browser.close()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt,EOFError):
        print('\n已取消，不保存会话。')
        raise SystemExit(1)
    except session.SessionError as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        # Never print a browser exception that might contain auth values.
        print('专用窗口登录 / 验证未完成，未确认导出成功。请检查窗口后重试。',file=sys.stderr)
        raise SystemExit(1)
