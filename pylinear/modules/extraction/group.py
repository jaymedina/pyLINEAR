import numpy as np
from shapely.geometry import Polygon
from scipy.spatial import ConvexHull

from pylinear import h5table
from pylinear.utilities import indices,pool,convexhull


TTYPE='DDT'

def groupFLT(flt,sources,extconf,path,minarea=0.1):
    
    
    # get the FLTs' polygons
    with h5table.H5Table(flt.dataset,TTYPE,path=path) as h5:

        for detname,detimg in flt:
            h5det=h5[detname]
            detconf=extconf[detname]
            
            for beam,beamconf in detconf:
                h5beam=h5det[beam]
                
                ids=[]
                polys=[]
                
                for segid,src in sources:
                    # read the DDT
                    ddt=h5table.DDT(src.segid)
                    ddt.readH5(h5beam)
                    if len(ddt)!=0:
                        
                        # collect the points accordingly
                        xyg=ddt.xyg.to_numpy
                        xyg=indices.unique(xyg)
                        x,y=indices.one2two(xyg,detimg.naxis)
                        del xyg

                        # get the vertices
                        xy=convexhull.vertices(x,y)

                        # reform to (x,y) pairs
                        xy=list(zip(*xy))

                        # make into a polygon from Shapely
                        poly=Polygon(xy)

                        # save the results
                        ids.append([segid])
                        polys.append(poly)
    # At this point, we've made shapely.Polygons out of each DDT
        

                        
    # now group those FLTs' 
    data=list(zip(ids,polys))
    nnew=ndata=len(ids)
    while nnew!=0:
        groups=[]


        while len(data)!=0:
            thisid,thispoly=data.pop(0)

            ids=thisid
            for i,(testid,testpoly) in enumerate(data):
                inter=thispoly.intersection(testpoly)
                area=inter.area
                if area>minarea:
                    thispoly=thispoly.union(testpoly)
                    data.pop(i)

                    ids.extend(testid)
            groups.append((ids,thispoly))
        data=groups
        nnew=ndata-len(data)
        ndata=len(data)

    # get just the IDs
    groups=list(zip(*groups))[0]


    # return a list of sets
    ids=[set(group) for group in groups]


    print(ids)
    q=input()
    
    return ids
        

def groupIDs(data):
    print("[info]Grouping the FLT groups")
    
    # group those IDs
    nnew=ndata=len(data)
    while nnew!=0:
        new=[]
        while len(data)!=0:
            this=data.pop(0)
            
            for i,test in enumerate(data):
                if len(this.intersection(test))!=0:
                    this=this.union(test)
                    data.pop(i)
            new.append(this)
        data=new
        n=len(data)
        nnew=ndata-n
        ndata=n
    return data


def makeGroups(conf,grisms,sources,extconf):
    print("[info]Starting the grouping algorithm")
   
    path=conf['tables']['path']
    
    # use the pool to group the FLTs
    p=pool.Pool(ncpu=conf['cpu']['ncpu'])
    ids=p(groupFLT,grisms.values,sources,extconf,path)
    print(ids)

    
    # group those IDs
    data=groupIDs(ids)
    
    # make data for output
    out=[datum for datum in data]

    # print something for something's sake
    print("[info]Done grouping. Found {} groups.".format(len(out)))
    
    return out
