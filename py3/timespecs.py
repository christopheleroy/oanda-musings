
import logging


def parse(specs):
    import re

    fetch = re.compile("([^=]+)=([^=,]+),?")
    found=[]
    while(len(specs)>1):
        mm = fetch.match(specs)
        if(mm is None):
            return found
        mmm = mm.group()
        tag = mm.groups()[1]
        subspecs = mm.groups()[0].split(",")
        compiledSubspecs = [weektimespec(x) for x in subspecs]
        logging.debug("For tag {}, approved timespecs: {}".format(tag,subspecs))
        found.append( (compiledSubspecs, tag) )
        specs = specs[ mm.end(): ]

    return found

def timeTag(tstamp, parsedSpecs, none=None):
    day,hr,min = weektimespec.ts2raw(tstamp)

    for spec in parsedSpecs:
        for wts in spec[0]:
            if(wts.isMatchRaw(day,hr,min)):
                return spec[1]

    return none





# expressions such as:

# mon-fri@9:30-16:30=close (daily-routine)
# mon@9:30-fri@16:30=close (week-span)
# mon-fri@8:15-16:45=email (daily-routine)


class weektimespec(object):
    def __init__(self,tspec):
        self.tspec = tspec
        self.startWeekDay = None
        self.endWeekDay = None
        self.startTime=None
        self.endTime=None
        self.mode = 'unk'

        self.parse()

    def  makeTime(self, hr,min,ending=False):
        hr = int(hr) % 24
        min = int(min) % 60

        tt = (hr*60.0+min)*60.0
        if(ending):
            tt = tt+59.9999
        return tt


    def parse(self):
        tspec = self.tspec.lower()

        import re
        # days as iso-days
        days = {"sun":7, "mon":1, "tue":2,
                "wed":3, "thu":4, "fri":5,
                "sat":6}
        dailyRoutine = re.compile(r"(sun|mon|tue|wed|thu|fri|sat)-(sun|mon|tue|wed|thu|fri|sat)@(\d+):(\d{2})-(\d+):(\d{2})")
        weekSpan = re.compile(r"(sun|mon|tue|wed|thu|fri|sat)@(\d+):(\d{2})-(sun|mon|tue|wed|thu|fri|sat)@(\d+):(\d{2})")


        dr = dailyRoutine.match(tspec)
        ws = weekSpan.match(tspec)
        mmap = ()

        if(dr is not None):
            ggg = dr.groups()
            mmap = (0,1,2,3,4,5)
            self.mode = 'daily-routine'
        elif(ws is not None):
            ggg = ws.groups()
            mmap = (0,3,1,2,4,5)
            self.mode = 'weekly-span'

        if(self.mode != 'unk'):
            self.startWeekDay = days[ggg[mmap[0]]]
            self.endWeekDay   = days[ggg[mmap[1]]]
            self.startTime = self.makeTime(ggg[mmap[2]], ggg[mmap[3]])
            self.endTime   = self.makeTime(ggg[mmap[4]], ggg[mmap[5]])
        else:
            raise ValueError("unable to parse {} correctly for a weektimespec".format(tspec))



    def isMatchRaw(self, day,hr,min):
        if( (self.startWeekDay < self.endWeekDay and (day < self.startWeekDay or day > self.endWeekDay)) or
            (self.startWeekDay == self.endWeekDay and day != self.startWeekDay) or
            (self.startWeekDay > self.endWeekDay and ( self.endWeekDay < day and day < self.startWeekDay)) ):
            return False

        hrminsec=(hr*60.0+min)*60.0


        if(self.mode == 'weekly-span'):
            if((day == self.startWeekDay and self.startTime > hrminsec) or
                (day== self.endWeekDay and self.endTime < hrminsec)):
                return False
            return True
        elif(self.mode == 'daily-routine'):
            if( (self.startTime > self.endTime and (self.startTime <= hrminsec or  hrminsec <= self.endTime)) or
                (self.startTime< self.endTime and self.startTime <= hrminsec and hrminsec <= self.endTime) or
                (self.startTime == self.endTime)):
                return True
            else:
                return False
        else:
            raise RuntimeError("weektimespec {} not parsed successfully, should not be used".format(self.tspec))


    def isMatch(self, timeX):
        day,hr,min = ts2raw(timeX)
        return self.isMatchRaw(day, hr,min)

    @staticmethod
    def ts2raw(timeX):
        import dateutil.parser,datetime
        if(type(timeX) is str): timeX = str(timeX)
        if(type(timeX) is str and timeX[4]=='-'):
            timeX = dateutil.parser.parse(timeX)
        elif(type(timeX) is int):
            timeX = datetime.from_timestamp(timeX)

        day = timeX.isoweekday()
        tt  = timeX.time()
        return (day, tt.hour, tt.minute)






#
# hello="mon-fri@9:30-16:30=open,mon-thu@18:30-07:30=openx,fri@15:30-sun@14:30=sleep"
#
# helloz = parse(hello)
#
# times=["06:35","07:27", "07:33", "08:45", "09:25","09:37","13:51", "14:14", "14:34","15:15","15:37","16:16",
#        "16:39", "17:22", "17:55", "18:21", "18:47", "19:24", "19:45","20:45"]
#
# days = [
#  ("wed", "02"), ("thu", "03"), ("fri", "04"), ("sat","05"), ("sun", "06"),("mon", "07"), ("tue", "08"), ("wed","09")]
#
# for d in days:
#     print "\n\n======================== {} =================".format(d[0])
#     for t in times:
#         tsp="2017-08-{}T{}:00.000000000Z".format(d[1],t)
#         tag = timeTag(tsp, helloz)
#         print "{} - {}".format(tsp,tag)
