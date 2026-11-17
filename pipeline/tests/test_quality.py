"""损坏数据与网络故障注入：证明错误能在发布前被发现和回滚。"""
import copy
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import data_quality as q
from refresh_all import transaction,freshness


class QualityTests(unittest.TestCase):
    def modified(self,file,change,check):
        original=q.read;value=copy.deepcopy(original(file));change(value)
        def read(name):return value if name in (file,'site/'+file) else original(name)
        with patch.object(q,'read',side_effect=read):
            with self.assertRaises((ValueError,KeyError,TypeError)):check()

    def test_real_release_files_pass(self):
        for name in q.MODULES:q.validate(name)
        q.cross_validate()

    def test_duplicate_date_is_rejected(self):
        self.modified('data.js',lambda x:x['daily']['dates'].__setitem__(-1,x['daily']['dates'][-2]),lambda:q.validate('daily'))

    def test_missing_whole_day_is_rejected(self):
        calendar=q.read('data-quality.json')['calendar']['dates']
        def change(x):
            for k in ('dates','amount','netflow','idx','nfCov','amtCov'):x['daily'][k].pop(-2)
        self.modified('data.js',change,lambda:q.check_calendar('daily',calendar))

    def test_missing_constituent_is_rejected(self):
        self.modified('funds.json',lambda x:x['funds'].pop('510300'),lambda:q.validate('funds'))

    def test_cross_module_gate_rejects_incomplete_directory_update(self):
        self.modified('funds.json',lambda x:x['funds'].pop('510300'),q.cross_validate)

    def test_flow_cannot_change_without_shares(self):
        self.modified('funds.json',lambda x:x['funds']['510300']['daily'][-1].__setitem__('flow',99999),lambda:q.validate('funds'))

    def test_wrong_amount_units_are_rejected(self):
        self.modified('data.js',lambda x:x['daily']['amount'].__setitem__(-1,x['daily']['amount'][-1]*10000),q.cross_validate)

    def test_missing_minute_cannot_be_zero_filled(self):
        self.modified('minute-history.json',lambda x:x['days'][x['calendar'][-1]].__setitem__(30,0),lambda:q.validate('minute'))

    def test_margin_audit_is_bound_to_published_numbers(self):
        self.modified('site/audit/market-coverage.json',lambda x:x['rows'][0].__setitem__('balanceYuan',1),lambda:q.validate('margin'))

    def test_null_nav_with_share_change_is_rejected(self):
        def change(x):
            a=x['funds']['510300']['daily'][-1];a.update(nav=None,aum=None,premium=None,shares=a['shares']+10)
        self.modified('funds.json',change,lambda:q.validate('funds'))

    def test_rounded_zero_flow_is_not_missing(self):
        x=q.read('funds.json');rows=[r for f in x['funds'].values() for r in f['daily']]
        self.assertTrue(any(r['flow']==0 for r in rows));q.validate('funds')

    def test_split_is_not_counted_as_subscription(self):
        rows={r['date']:r for r in q.read('funds.json')['funds']['512220']['daily']}
        before,after=rows['2026-11-04'],rows['2026-11-05']
        expected=(after['shares']-before['shares']*3)*after['nav']
        self.assertAlmostEqual(after['flow'],expected,places=5)
        self.assertLess(after['flow'],0)
        self.assertAlmostEqual(after['premium'],(after['close']/3/after['nav']-1)*100,places=3)

    def test_unknown_nav_jump_is_blocked_even_when_identities_match(self):
        def change(x):
            r=x['funds']['510300']['daily'][-1];r['nav']/=3;r['aum']=round(r['shares']*r['nav'],6)
            r['flow']=round((r['shares']-x['funds']['510300']['daily'][-2]['shares'])*r['nav'],6)
            r['premium']=round((r['close']/r['nav']-1)*100,4)
        self.modified('funds.json',change,lambda:q.validate('funds'))

    def test_weekend_lag_uses_trading_days(self):
        cal=['2026-11-12','2026-11-13','2026-11-16','2026-11-17']
        self.assertEqual(freshness('daily','2026-11-13',cal,datetime(2026,11,16,9,tzinfo=q.ZONE))['lag'],0)
        self.assertEqual(freshness('daily','2026-11-13',cal,datetime(2026,11,17,9,tzinfo=q.ZONE))['lag'],1)
        self.assertEqual(freshness('themes','2026-11-16',cal,datetime(2026,11,17,14,tzinfo=q.ZONE))['lag'],0)
        self.assertEqual(freshness('themes','2026-11-16',cal,datetime(2026,11,17,16,tzinfo=q.ZONE))['lag'],1)

    def test_failed_candidate_is_restored_and_other_module_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'a').write_bytes(b'valid');(root/'b').write_bytes(b'other')
            with patch.object(q,'ROOT',root),patch.object(q,'MODULES',{'a':['a'],'b':['b']}),patch.object(q,'latest',return_value='2026-11-16'),patch.object(q,'validate',return_value={}),patch.object(q,'cross_validate'):
                def bad():
                    (root/'a').write_bytes(b'partial')
                    raise ConnectionError('源站中断')
                result=transaction('a',bad)
                self.assertFalse(result['ok']);self.assertEqual(result['failureType'],'source');self.assertEqual((root/'a').read_bytes(),b'valid')
                result=transaction('b',lambda:(root/'b').write_bytes(b'newvalid'))
                self.assertTrue(result['ok']);self.assertEqual((root/'b').read_bytes(),b'newvalid')
                with patch.object(q,'validate',side_effect=ValueError('单位错误')):
                    result=transaction('a',lambda:(root/'a').write_bytes(b'badunits'))
                    self.assertEqual(result['failureType'],'validation');self.assertEqual((root/'a').read_bytes(),b'valid')

    def test_file_changed_after_validation_cannot_publish(self):
        with patch.object(q,'hashes',return_value={'x':'changed'}):
            with self.assertRaisesRegex(ValueError,'尚未完成校验'):q.validate_release()


if __name__=='__main__':unittest.main()
