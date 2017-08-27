import unittest

class TestTimeSpecs(unittest.TestCase):

    def test_01_parse(self):
        hello="mon-fri@9:30-16:30=open,mon-thu@18:30-07:30=openx,fri@15:30-sun@14:30=sleep"
        hello2="mon-fri@9:30-16:30,mon-thu@18:30-07:30=openx,fri@15:30-sun@14:30=sleep"
        #
        import timespecs

        parsed = timespecs.parse(hello)

        self.assertTrue(len(parsed)==3)
        self.assertTrue(parsed[0][1] == 'open')
        self.assertTrue(parsed[2][1]=='sleep')
        self.assertTrue(len(parsed[0][0])==1)

        parsed = timespecs.parse(hello2)

        self.assertTrue(len(parsed)==2)
        self.assertTrue(parsed[0][1] == 'openx')
        self.assertTrue(parsed[1][1]=='sleep')
        self.assertTrue(len(parsed[0][0])==2)


        badhello="mon-fri@9:30-16:30=open,mon-thu/18:30-07:30=openx,fri@15:30-sun@14:30=sleep"
        with self.assertRaises(ValueError):
            timespecs.parse(badhello)


    def test_02_match_raw(self):

        hello="mon-fri@9:30-16:30=success"

        import timespecs, datetime

        parsed = timespecs.parse(hello)

        for d in range(1,7):
            for hr in range(0,24):
                for min in [25,35]:
                    expect = "success"
                    if(d<1 or d>5):
                        expect = None
                    elif(hr<9 or hr>16):
                        expect = None
                    elif((hr==9 and min < 30) or (hr==16 and min>30)):
                        expect = None

                    valBool = parsed[0][0][0].isMatchRaw(d,hr,min)
                    ztime = datetime.datetime(2011,8,d, hr,min,0).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
                    val = timespecs.timeTag(ztime, parsed)
                    if(expect is None):
                        self.assertTrue(val is None)
                        self.assertFalse(valBool)
                        self.assertEquals( timespecs.timeTag(ztime, parsed, 'nothing, thanks'),'nothing, thanks')
                    else:
                        self.assertEquals(val, "success")
                        self.assertTrue(valBool)




if __name__ == '__main__':
    unittest.main()
