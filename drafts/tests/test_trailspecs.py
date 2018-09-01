

import unittest, pdb

class BogusC(object):
    def __init__(self, open,close=None,high=None,low=None):
        self.o = open
        self.c = open if (close is None) else close
        self.h = open if (high is None) else high
        self.l = open if (low is None) else low

class BogusQ(object):
    def __init__(self, time, ask, bid = None, mid = None):
        self.time = time
        self.ask = ask
        self.bid = ask if(bid is None) else bid
        if(mid is None):
            self.mid =  BogusC((self.ask.o+self.bid.o)/2, (self.ask.c+self.bid.c)/2)
        else:
            self.mid = mid

show_off = False

def show(pos, tag = None):
    global show_off

    if(pos == 'off'):
        show_off = True
        return
    if(pos == 'on'):
        show_off = False
        return
    if(show_off): return

    if(pos is None):
        print(("traiing-stop", "trigger-price", "value", "distnace",
               "desired-distance", "needs-replacement"))
        return

    print((tag, pos.trailingStopTriggerPrice, 
              pos.trailingStopValue,pos.trailingStopDistance, 
              pos.trailingStopDesiredDistance, pos.trailingStopNeedsReplacement))

def mkt(minutes):
    d = '2018-08-21T'
    h = 13
    m = 11
    m = m+minutes
    while(m>60):
        h += 1
        m -= 60
    mm = str(m)
    if(len(mm)<2): mm = "0"+mm
    return d + str(h) + ":" + mm + ":00.000000000Z"


def simulate(pos, wow, currentQuote, mspread,minTS):
    if(wow[0] == 'trailing-stop' and wow[1] == 'trailing-update'):
        pos.trailingStopDistance = pos.trailingStopDesiredDistance
        # if(pos.trailingStopDistance < minTS): pos.trailingStopDesiredDistance = minTS
        rprice = pos.relevantPrice(currentQuote)
        pos.trailingStopValue = rprice - (1.0 if(pos.forBUY) else -1.0)* pos.trailingStopDistance
        pos.trailingStopNeedsReplacement = False
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(currentQuote, None, None, None)
        return
    if(wow[0] == 'hold'):
        return
    raise ValueError("cannot work with " + wow[0])


class TestTrailSpecs(unittest.TestCase):

    def check(self, pos, expTriggerPrice, expStopValue, expStopDistance, expDesiredDistance,expReplacementNeeded=False):
        self.assertAlmostEqual(pos.trailingStopTriggerPrice, expTriggerPrice)
        self.assertAlmostEqual(pos.trailingStopDistance, expStopDistance)
        self.assertEqual(pos.trailingStopNeedsReplacement, expReplacementNeeded)
        self.assertAlmostEqual(pos.trailingStopDesiredDistance, expDesiredDistance)
        self.assertAlmostEqual(pos.trailingStopValue, expStopValue)

    def test_simple_BUY(self):
        trailSpecs = [(10.0, 10.0), (12.0, 9.0), (15.0, 8.0), (20.0, 5.0), (30.0, 3.0), (40.0, 2.0)]
        # assume a BUY position at 100, with take profit 120 and save loss 90 (quantity=1234)
        # spread is 0.21, minimum trailing stop distance 0.55

        from myt_support import Position

        show('off')
        show(None)
        now = mkt(1) # '2018-08-21T13:12:00.000000000Z'
        now100C = BogusC(100)
        now100Q = BogusQ(now, now100C)
        mspread = 0.21
        minTS = 0.55

        pos = Position(True, now100Q, 1234, 90.0, 120.0)

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
        show(pos, 'initially')
        
        # now we simulate price fluctuations, but we never make the stop-loss distance changes.
        then = mkt(5)
        then105Q = BogusQ(then, BogusC(105))

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
        show(pos, 'for 105')
        pos.updateTrailingStopValue(then105Q)
        show(pos, 'for 105 after update')
        obsv = (105-100)/mspread;xpf = 5.0;xp = xpf*mspread
        self.check(pos, 102.1, None, None, xp, True)


        pos = Position(True, now100Q, 1234, 90.0, 120.0)    
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
        then = mkt(7)
        then106Q = BogusQ(then, BogusC(106))

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then106Q, trailSpecs, mspread, minTS)

        show(pos, 'for 106')
        pos.updateTrailingStopValue(then106Q)
        show(pos, 'for 106 after update')
        obsv = (106-100)/mspread;xpf = 5.0;xp = xpf*mspread
        self.check(pos, 102.1, None, None, xp, True)

        pos = Position(True, now100Q, 1234, 90.0, 120.0)    
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
        then = mkt(10)
        then101Q = BogusQ(then, BogusC(101))

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then101Q, trailSpecs, mspread, minTS)

        show(pos, 'for 101')
        pos.updateTrailingStopValue(then101Q)
        show(pos, 'for 101 after update')
        xp = 10*mspread
        self.check(pos, 102.1, None, None, xp, False)

        then = mkt(12)
        then112Q = BogusQ(then, BogusC(112))

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then112Q, trailSpecs, mspread, minTS)

        show(pos, 'for 112')
        pos.updateTrailingStopValue(then112Q)
        show(pos, 'for 112 after update')
        obsv = (112-100)/mspread;xpf = 2.0;xp = xpf*mspread; xp = minTS # too small
        self.check(pos, 102.1, None, None, 0.55, True)


    def test_simple_SELL(self):
            trailSpecs = [(10.0, 10.0), (12.0, 9.0), (15.0, 8.0), (20.0, 5.0), (30.0, 3.0), (40.0, 2.0)]
            # assume a SELL position at 100, with take profit 80 and save loss 110 (quantity=1234)
            # spread is 0.21, minimum trailing stop distance 0.55

            from myt_support import Position

            show('off')
            show(None)
            now = mkt(1) # '2018-08-21T13:12:00.000000000Z'
            now100C = BogusC(100)
            now100Q = BogusQ(now, now100C)
            mspread = 0.21
            minTS = 0.55

            # forBUY = False ==> for SELL!
            forSELL = False 
            pos = Position(False, now100Q, 1234, 90.0, 120.0)

            pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
            show(pos, 'initially')
            
            # now we simulate price fluctuations, but we never make the stop-loss distance changes.
            then = mkt(5)
            then105Q = BogusQ(then, BogusC(95))

            
            pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
            show(pos, 'for 95')
            pos.updateTrailingStopValue(then105Q)
            show(pos, 'for 95 after update')
            obsv = (100-95)/mspread;xpf = 5.0;xp = xpf*mspread
            self.check(pos, 97.9, None, None, xp, True)


            pos = Position(forSELL, now100Q, 1234, 90.0, 120.0)    
            pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
            then = mkt(7)
            then106Q = BogusQ(then, BogusC(94))
            # pdb.set_trace()
            pos.calibrateTrailingStopLossDesireForSteppedSpecs(then106Q, trailSpecs, mspread, minTS)

            show(pos, 'for 94')
            pos.updateTrailingStopValue(then106Q)
            show(pos, 'for 94 after update')
            obsv = (100-94)/mspread;xpf = 5.0;xp = xpf*mspread
            self.check(pos, 97.9, None, None, xp, True)

            pos = Position(forSELL, now100Q, 1234, 90.0, 120.0)    
            pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
            then = mkt(10)
            then101Q = BogusQ(then, BogusC(99))

            pos.calibrateTrailingStopLossDesireForSteppedSpecs(then101Q, trailSpecs, mspread, minTS)

            show(pos, 'for 99')
            pos.updateTrailingStopValue(then101Q)
            show(pos, 'for 99 after update')
            xp = 10*mspread
            self.check(pos, 97.9, None, None, xp, False)

            then = mkt(12)
            then112Q = BogusQ(then, BogusC(88))
            # pdb.set_trace()
            pos.calibrateTrailingStopLossDesireForSteppedSpecs(then112Q, trailSpecs, mspread, minTS)

            show(pos, 'for 88')
            pos.updateTrailingStopValue(then112Q)
            show(pos, 'for 88 after update')
            obsv = (100-88)/mspread;xpf = 2.0;xp = xpf*mspread; xp = minTS # too small
            self.check(pos, 97.9, None, None, 0.55, True)


    def test_real_BUY(self):
        trailSpecs = [
            (10.0, 10.0), (12.0, 9.0),
            (15.0, 8.0), (20.0, 5.0), 
            (30.0, 3.0), (40.0, 2.0)
        ]
        # assume a BUY position at 100, with take profit 120 and save loss 90 (quantity=1234)
        # spread is 0.21, minimum trailing stop distance 0.55

        from myt_support import Position

        show('off')
        show(None)
        now = mkt(1) # '2018-08-21T13:12:00.000000000Z'
        now100C = BogusC(100)
        now100Q = BogusQ(now, now100C)
        mspread = 0.21
        minTS = 0.55

        pos = Position(True, now100Q, 1234, 90.0, 120.0)

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
        show(pos, 'initially')
        

        then = mkt(3)
        then105Q = BogusQ(then, BogusC(105))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
        show(pos, 'for 105')
        pos.updateTrailingStopValue(then105Q)
        # pdb.set_trace()
        wow = pos.timeToClose(then105Q, None)
        
        # print(wow)
        simulate(pos, wow, then105Q, mspread, minTS)
        show(pos, 'for 105 after update')
        xp =1.05
        self.check(pos, 102.1, 105 - xp, xp, xp, False)

        then = mkt(5)
        then104Q = BogusQ(then, BogusC(104))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then104Q, trailSpecs, mspread, minTS)
        show(pos, 'for 104')
        pos.updateTrailingStopValue(then104Q)
        # pdb.set_trace()
        wow = pos.timeToClose(then104Q,None)
        self.assertEqual(wow[0], 'hold')
        simulate(pos, wow, then104Q, mspread, minTS)
        
        then = mkt(7)
        then105iQ = BogusQ(then, BogusC(105.5))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105iQ, trailSpecs, mspread, minTS)
        show(pos, 'for 105.5')
        pos.updateTrailingStopValue(then105iQ)
        show(pos,'for 105.5 after update')
        # pdb.set_trace()
        wow = pos.timeToClose(then105iQ,None)
        self.check(pos, 102.1, 104.45, 1.05,1.05,False)
        self.assertEqual(wow[0], 'hold')
        simulate(pos, wow, then105iQ, mspread, minTS)
        show(pos, 'for 105.5 after X')
        then = mkt(9)
        then108Q = BogusQ(then, BogusC(108))
        # pdb.set_trace()
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then108Q, trailSpecs, mspread, minTS)
        show(pos, 'for 108')
        pos.updateTrailingStopValue(then108Q)
        show(pos, 'for 108 after update')
        wow = pos.timeToClose(then108Q,None)
        self.assertEqual(wow[1], 'trailing-update')
        self.assertEqual(wow[2], 8.0)
        # pdb.set_trace()
        simulate(pos, wow, then108Q, mspread, minTS)
        show(pos, 'for 108 X')
        
        # print(wow)
        then = mkt(11)
        then105Q = BogusQ(then, BogusC(105))
        # pdb.set_trace()
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
        show(pos, 'for 1085ii')
        pos.updateTrailingStopValue(then105Q)
        show(pos, 'for 105ii after update')
        wow = pos.timeToClose(then105Q,None)
        self.assertEqual(wow[1], 'close')
        # self.assertEqual(wow[2], 8.0)
        # pdb.set_trace()
        # simulate(pos, wow, then108Q, mspread, minTS)
        # show(pos, 'for 105ii X')
        

    def test_real_SELL(self):
        trailSpecs = [
            (10.0, 10.0), (12.0, 9.0),
            (15.0, 8.0), (20.0, 5.0), 
            (30.0, 3.0), (40.0, 2.0)
        ]
        # assume a SELL position at 100, with take profit 80 and save loss 110 (quantity=1234)
        # spread is 0.21, minimum trailing stop distance 0.55

        from myt_support import Position

        show('off')
        show(None)
        now = mkt(1) # '2018-08-21T13:12:00.000000000Z'
        now100C = BogusC(100)
        now100Q = BogusQ(now, now100C)
        mspread = 0.21
        minTS = 0.55

        forSELL = False # because we do want to SELL
        pos = Position(forSELL, now100Q, 1234, 110, 80)

        pos.calibrateTrailingStopLossDesireForSteppedSpecs(None, trailSpecs, mspread,minTS)
        show(pos, 'initially')
        

        then = mkt(3)
        then105Q = BogusQ(then, BogusC(95))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
        show(pos, 'for 95')
        pos.updateTrailingStopValue(then105Q)
        # pdb.set_trace()
        wow = pos.timeToClose(then105Q, None)
        
        # print(wow)
        simulate(pos, wow, then105Q, mspread, minTS)
        show(pos, 'for 95 after update')
        xp =1.05
        self.check(pos, 97.9, 95+xp, xp, xp, False)

        then = mkt(5)
        then104Q = BogusQ(then, BogusC(96))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then104Q, trailSpecs, mspread, minTS)
        show(pos, 'for 96')
        pos.updateTrailingStopValue(then104Q)
        # pdb.set_trace()
        wow = pos.timeToClose(then104Q,None)
        self.assertEqual(wow[0], 'hold')
        simulate(pos, wow, then104Q, mspread, minTS)
        
        then = mkt(7)
        then105iQ = BogusQ(then, BogusC(94.5))
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105iQ, trailSpecs, mspread, minTS)
        show(pos, 'for 94.5')
        pos.updateTrailingStopValue(then105iQ)
        show(pos,'for 94.5 after update')
        # pdb.set_trace()
        wow = pos.timeToClose(then105iQ,None)
        self.check(pos, 97.9, 95.55, 1.05,1.05,False)
        self.assertEqual(wow[0], 'hold')
        simulate(pos, wow, then105iQ, mspread, minTS)
        show(pos, 'for 94.5.5 after X')
        then = mkt(9)
        then108Q = BogusQ(then, BogusC(92))
        # pdb.set_trace()
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then108Q, trailSpecs, mspread, minTS)
        show(pos, 'for 92')
        pos.updateTrailingStopValue(then108Q)
        show(pos, 'for 92 after update')
        wow = pos.timeToClose(then108Q,None)
        self.assertEqual(wow[1], 'trailing-update')
        self.assertEqual(wow[2], 8.0)
        # pdb.set_trace()
        simulate(pos, wow, then108Q, mspread, minTS)
        show(pos, 'for 108 X')
        
        # print(wow)
        then = mkt(11)
        then105Q = BogusQ(then, BogusC(95))
        # pdb.set_trace()
        pos.calibrateTrailingStopLossDesireForSteppedSpecs(then105Q, trailSpecs, mspread, minTS)
        show(pos, 'for 95ii')
        pos.updateTrailingStopValue(then105Q)
        show(pos, 'for 95ii after update')
        wow = pos.timeToClose(then105Q,None)
        self.assertEqual(wow[1], 'close')
        # self.assertEqua105ii X')
        



if __name__ == '__main__':
    unittest.main()
