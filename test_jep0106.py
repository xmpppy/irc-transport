#!/usr/bin/python
import jep0106
from jep0106 import *

def test(before):
	during = JIDEncode(before)
	after = JIDDecode(during)
	if after == before:
		print 'PASS Before: ' + before
		print 'PASS During: ' + during
	else:
		print 'FAIL Before: ' + before
		print 'FAIL During: ' + during
		print 'FAIL After : ' + after
	print

test('jid escaping')
test(r'\3and\2is\5@example.com')
test(r'\3catsand\2catsis\5cats@example.com')
test(r'\2plus\2is\4')
test(r'foo\bar')
test(r'foob\41r')
test('here\'s_a wild_&_/cr%zy/_address@example.com')
