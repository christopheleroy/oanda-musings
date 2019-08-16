import logging


def superimpose(parser,args, defaults, securitySets=[]):

    # when defaults is a list, we apply the correct defaults
    toApply = []
    if(type(defaults) is dict):
        toApply.append(defaults)
    else:
        for d in defaults:
            if(type(d) is not dict):
                import pdb; pdb.set_trace()
            if("for" in d):
                if(type(d["for"]) is dict):
                    for k,v in d["for"].items():
                        try:
                            av = getattr(args, k)
                            if(av == v):
                                toApply.append(d["defaults"])
                                break
                        except:
                            pass
                elif(d["for"]=="*"):
                    toApply.append(d["defaults"])
            elif("security" in d):
                for s in d["security"]: securitySets.append(s)


    if(len(toApply)==0):
        logging.info("not default found to apply...")

    argsChangeDict={}
    problems = 0
    for defs in toApply:
        localChanges = []
        for defk,defv in defs.items():
            for opt in parser._actions:
                if(defk == opt.dest):
                    if(type(defv) != opt.type and opt.type is not None):
                        raise ValueError("Default value {} is not of type {}".format(defv, opt.type))

                    argVal = getattr(args, defk)
                    if( (opt.default is None and (argVal is None and defv is not None)) or
                        (opt.default is not None and ((not argVal != opt.default) and defv is not None)) ):
                        logging.debug("imposing default param {} ==> {}".format(defk,defv))
                        setattr(args, defk, defv)
                        argsChangeDict[defk] = defv
                        localChanges.append(defk)
        # make sure the local-changes are always satisfy all security sets
        for ss in securitySets:
            #items that are in security set ss and in localChanges
            intersection = [ f for f in ss if f in localChanges ]
            missing = [ f for f in ss if f not in localChanges]
            if(len(intersection)>0 and len(missing)>0):
                logging.critical("Security Sets for SuperImposeArgs, missing: {}".format(missing))
                problems+=1


    if(problems>0):
        raise RuntimeError("superimpose security sets violated...")
    return argsChangeDict


def superimposeFromFile(parser, args, jsonFile, securitySets=[]):
    import json

    with open(jsonFile, 'rb') as jf:
        defaults = json.load(jf)
        return superimpose(parser,args,defaults,securitySets)
