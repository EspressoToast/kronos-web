"""List online futures products or fetch latest bars without opening the UI."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webui.market_data import catalog, download, PERIODS

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--node',help='Product ID from --list, e.g. zly_qh')
    parser.add_argument('--period',choices=list(PERIODS),default='30')
    args=parser.parse_args()
    if args.list:
        for item in catalog()['items']:
            print(item['id'], item['exchange_name'], item['name'])
    elif args.node:
        print(download(args.node,args.period))
    else: parser.error('Use --list or --node')
