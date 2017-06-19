
from teeth import findExtremes


def pmpackem(z, toffset=0, tstep=1, f=(lambda x: x)):
    packed = []
    for i,val in enumerate(z):
        packed.append( {"t": (i*tstep+toffset), "v": f(val) })

    return packed

def pmpt(x):
    return x["t"]


def pmpv(x):
    return x["v"]

ch2inc = {"=": 0, "-": -1, "_": -2, "~":-3, "+": 1, "!":2, "|":3}

def pgenerate(init=1,seq = "==++==++==-==~|===="):
    arr = [ init ]
    for ch in seq: arr.append(arr[-1]+ch2inc[ch])
    return arr

def findNext(q,n,ab):
    m = n+1
    while(m<len(q)):
        if(ab[m]):
            return "swing: " + (str(pmpv(q[m]) - pmpv(q[n]))) + " - length: " + str(m-n)
        m=m+1
    return "n/a"


def display(q,a,b):
    for n in range(len(q)):
        if(a[n]):
            print "Min@" + str(n) + ":  " + str(q[n]) + " " + findNext(q,n,b)
        if(b[n]):
            print "Max@" + str(n) + ":  " + str(q[n]) + " " + findNext(q,n,a)

def show(seq, init, nlevel):
    q = pmpackem(pgenerate(init, seq))
    # print q
    a,b = findExtremes(q,pmpv, pmpt,nlevel,1)
    print "input:  " + seq
    mxn = "lvl "+ str(nlevel) +": "
    for n in range(len(q)):
        ch = " "
        if(a[n]): ch = "."
        if(b[n]): ch = "^"
        mxn = mxn + ch
    print mxn
    display(q,a,b)


show("==++++==+___==+++||+====------=---===++===_____====", 100, 3)
print ""
show("==++++==+___==+++||+====------=---===++===_____====", 100, 2)
print ""
show("==++++==+___==+++||+====------=---===++===_____====", 100, 5)
print ""


# q0 = [1,2,3,4,5,7,6,5,4,3,2,3,4,5,6,7,8,9,7,9,6,5,4,3,2,1]
# q = pmpackem(q0)
#
# a,b = findExtremes(q,pmpv,pmpt,3,1)
#
# display(q0,a,b)
#
# import math
# p11 = 4*math.atan(1)/11
#
# q1 = [ {"v": math.sin(x*p11), "t": x*3+7} for x in range(145) ]
# a,b = findExtremes(q1,pmpv,pmpt,4,3)
#
# display(q1,a,b)
#
#
# q2 = [ 1,2,3,4,5,6,7,6,7,6,5,6,7,7,6,5,8,9,10,11,8,9,10,11,14,14,14,14,14,11,10,9,9,9,1]
# q = pmpackem(q2)
#
# a,b = findExtremes(q,pmpv, pmpt,3,1)
# print "For level 3:"
# display(q,a,b)
#
# print ""
# print "for level 4:"
# a,b = findExtremes(q,pmpv, pmpt,4,1)
# display(q,a,b)
