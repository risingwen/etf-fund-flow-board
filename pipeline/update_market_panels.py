"""独立更新三个资金模块，失败保留原文件并公开最近更新状态。"""
import sys
import traceback

from market_common import SITE, save_json, stamp
from update_etf_margin import update as margin
from update_leverage import update as leverage
from update_themes import update as themes


def main():
    status = {'version':1,'checkedAt':stamp(),'modules':{}}
    failed = False
    for name, operation in [('margin',margin),('leverage',leverage),('themes',themes)]:
        try:
            operation()
            status['modules'][name] = {'ok':True}
        except Exception as error:
            failed = True
            # 页面只公开一般状态，详细错误留在任务日志，避免泄露环境信息。
            status['modules'][name] = {'ok':False}
            print(f'{name} 更新失败，保留已发布文件：{type(error).__name__}',flush=True)
            traceback.print_exc()
    save_json(SITE/'market-status.json',status)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
