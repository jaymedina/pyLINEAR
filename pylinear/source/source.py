import numpy as np


from .extractionparameters import ExtractionParameters
from pylinear.synthphot import SED
from pylinear.astro import WCS
from pylinear.utilities import convexhull



class Source(WCS,ExtractionParameters):
    SEGTYPE=np.uint32           # force SEGIDs to have this type

    def __init__(self,img,seg,zero,segid=None,minpix=0,\
                 lamb0=None,lamb1=None,dlamb=None):

        #get the SEGID
        if segid is None:
            if 'SEGID' in seg.header:
                segid=seg.header['SEGID']
            else:
                print('[alarm]Segmentation ID is missing from header.')
                self.valid=False
                return

        self.segid=self.SEGTYPE(segid)
        
        # get the good pixels
        g=np.where(seg.data == self.segid)
        self.npix=len(g[0])
        if self.npix<=minpix:
            print("[warn]Too few pixels ({}) for {} ".format(self.npix,self.segid))


            
            
        # check that the img/seg astrometry matches
        keys=['NAXIS','NAXIS2','CRPIX1','CRPIX2','CRVAL1','CRVAL2', \
              'CD1_1','CD1_2','CD2_1','CD2_2','CTYPE1','CTYPE2']
        for key in keys:
            if img[key]!=seg[key]:
                print('[alarm]Incompatible headers for {}'.format(self.segid))
                self.valid=False
                return
        
        
        # initialize an SED object
        self.sed=SED()

        # initialize the header
        WCS.__init__(self,seg.header)  # could be seg or img here

        
        # initialize the extraction parameters
        ExtractionParameters.__init__(self,lamb0,lamb1,dlamb)

        # compute the area of this source
        self.area=self.npix*self.pixelarea

        # recall that Python & IDL are inverted
        self.xd=g[1]      # direct image x-coordinates
        self.yd=g[0]      # direct image y-coordinates

        # compute a few brightness measures
        self.total=np.sum(img.data[g])
        if self.total >0:
            self.mag=-2.5*np.log10(self.total)+zero
            self.wht=img.data[g]/self.total

            # compute the centroids (in pixel and RA,Dec)
            self.xyc=np.array([np.average(self.xd,weights=self.wht), \
                               np.average(self.yd,weights=self.wht)])
            self.adc=np.array(self.xy2ad(self.xyc[0],self.xyc[1]))

        else:
            print('[alarm]Negative flux in source {}'.format(self.segid))
            self.valid=False
            return

        self.valid=True
            
        
    def instrumentalFlux(self,img):
        ''' compute the instrumental flux of this source in an image '''
        xd=self.xd-int(self.ltv[0])
        yd=self.yd-int(self.ltv[1])
        tot=np.sum(img.data[yd,xd])
        return tot

    @property
    def convexHull(self):
        #dx=[0,0,1,1]
        #dy=[0,1,1,0]
        #points=[]
        #for x,y in zip(dx,dy):
        #    xx=self.xd+x
        #    yy=self.yd+y
        #    points.extend(list(zip(xx,yy)))
        #points=np.array(list(set(points)))#
        #
        #print(points.shape)
        #
        #
        #points=np.array([self.xd,self.yd]).T
        #print(points.shape)
        #hull=ConvexHull(points)
        #
        #xh,yh=[],[]
        #for vertex in hull.vertices:
        #    xh.append(points[vertex,0])
        #    yh.append(points[vertex,1])
        #xh,yh=np.array(xh),np.array(yh)
        
        #return xh,yh

        return convexhull.vertices(self.xd,self.yd)
    
    @property
    def name(self):
        return '{}'.format(self.segid)
    

    def __str__(self):
        return 'Source segid={}'.format(self.segid)

    def __iter__(self):
        for x,y,w in zip(self.xd,self.yd,self.wht):
            yield x,y,w

    def __len__(self):
        return len(self.xd)
