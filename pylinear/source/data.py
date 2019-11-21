import os
import numpy as np
from astropy.io import fits
from collections import OrderedDict
import tqdm
import copy
import pdb


from fitsimage import FITSImage

from .source import Source
from .obslst import ObsLST
from pylinear.utilities import indices


class Data(object):
    SEGTYPE=np.uint32           # force SEGIDs to have this type
    PREFIX='{:6d}'
    def __init__(self,conf):
        print('[info]Loading OBSLST')
        
        # load the obs data
        self.obsdata=ObsLST(conf)

        # save the segmap
        self.segmap=conf['segmap']
        
        # load the segmentation map
        self.sources=OrderedDict()
        
        # read the segmentation map
        with fits.open(self.segmap) as hdus:

            # read the detection image
            with fits.open(self.obsdata.detImage) as hdui:

                # require that the detection & segmentation images are
                # compatable
                assert (len(hdus) == len(hdui)),'Invalid image dimensions'

                # load according to how many extensions
                if len(hdus)==1:
                    self.fromClassic(conf,hdus,hdui)
                else:
                    self.fromMEF(conf,hdus,hdui)

        # rmeove sources below the magnitude limit
        try:
            self.maglimit=conf['maglim']
        except:
            self.maglimit=None
        self.applyMagLimit(self.maglimit)
        
        # set the default spectra as photometry
        self.loadPhotometry()

        # verify some things
        if not self.sources:
            raise RuntimeError("No sources are valid.")
        
    def __contains__(self,key):
        return key in self.sources 
    
    def __len__(self):
        return len(self.sources)

    def __str__(self):
        t='{} sources: \n'.format(str(len(self.sources)))
        t=t+str(list(self.sources.keys()))
        return t

    def __iter__(self):
        #yield from self.sources.items()
        for args in self.sources.items():
            yield args

    def __getitem__(self,segid):
        return self.sources[segid]
    def __setitem__(self,segid,src):
        if isinstance(src,Source):
            if segid in self.sources:
                print("[alarm]Duplicate SEGIDs are ignored: {}".format(segid))
            else:
                if src.valid:
                    self.sources[self.SEGTYPE(segid)]=src

    def keyword(self,key,hdr,conf):
        ''' utility to logically get a value from either a header or global '''

        for k in [key,key.lower(),key.upper()]:   # test all combinations
            if k in hdr:
                return hdr[k]
            if k in conf:
                return conf[k]

        return None
                    

    #def setExtractionParameter(self,src,conf,extconf,key):
    #    if getattr(src,key) is None:
    #        val=conf[key]
    #        if val is None:
    #            val=getattr(extconf,key)
    #        
    #        setattr(src,key,val)
                
    def setExtractionParameters(self,conf,extconf):
        print('[info]Setting extraction parameters') 
        for segid,src in self.sources.items():
            for key in ('lamb0','lamb1','dlamb'):
                if getattr(src,key) is None:
                    val=conf[key]
                    if val is None:
                        val=getattr(extconf,key)
                    setattr(src,key,val)

                    
                #self.setExtractionParameter(src,conf,extconf,key)
                    
    def keys(self):
        return self.sources.keys()

    def values(self):
        return list(self.sources.values())

    def select(self,segids):
        ''' return a Data class with new segIDs set. '''
        
        out=copy.deepcopy(self)        # create an output class
        keep=set(segids)               # the IDs we want in the output
        has=set(self.sources.keys())   # the IDS we have in original
        remove=has.difference(keep)    # the IDs to remove 

        # remove the IDs
        for r in remove:
            del out.sources[r]

        #out=copy.deepcopy(self)
        #out.sources={segid: self.sources[segid] for segid in segids}
       
        return out

    

    def loadPhotometry(self):
        ''' load photometry for each source as a crude SED '''
        print('[info]Loading broadband phototmetry')


        fluxunit=1.    # the old way... will deprecate in time.
        
        lamb,flam=[],[]

        for name,filt,zero in self.obsdata:
            lamb.append(filt.photplam)
            img=FITSImage(name,0)
            f=[]
            for segid,src in self.sources.items():
                tot=src.instrumentalFlux(img)
                f.append(tot*(filt.photflam/fluxunit))
            flam.append(f)

        lamb=np.array(lamb)
        flam=list(zip(*flam))

        for (segid,src),f in zip(self.sources.items(),flam):
            src.sed.lamb=lamb
            src.sed.flam=np.array(f)
            

    def applyMagLimit(self,maglimit):
        ''' apply a magnitude limit cut '''
            
        if maglimit is not None:
            print('[info]Apply magnitude limit: {}'.format(maglimit))
            sources=OrderedDict()
            for segid,src in self.sources.items():
                if src.mag < maglimit:
                    sources[segid]=src
            n=len(sources)
            if n==0:
                raise RuntimeError("All sources too faint.")

            print('[info]Magnitude limit: {} \u27f6  {}'.format(len(self),n))
            self.sources=sources

            

    def fromClassic(self,conf,seglist,imglist):
        ''' load sources via a classic segmentation map '''
        print('[info]Loading sources from CLASSIC segmentation map')


        # load the images
        exten=0
        seg=FITSImage(seglist,exten)
        img=FITSImage(imglist,exten)
        
        # get the reverse indices (is potentially slow)
        revind=indices.reverse(seg.image.astype(self.SEGTYPE))
        if revind[0][0]==0:
            del revind[0]     # remove the sky index from the segmentation


        # get a progress bar
        #pb=progressbar.ProgressBar(len(revind))
        pb=tqdm.tqdm(total=len(revind),dynamic_ncols=True,desc='Classic Segmap')

        # get the detection filter
        detzpt=self.obsdata.detZeropoint
            
        # process each index
        for segid,ri in revind:
            # set the prefix
            #pb.prefix=self.PREFIX.format(segid)            
            pb.desc=self.PREFIX.format(segid)
            
            # compute (x,y) pairs
            x,y=indices.one2two(ri,seg.shape)

            # get bounding box
            x0,x1=np.amin(x),np.amax(x)
            y0,y1=np.amin(y),np.amax(y)

                        
            # call something like hextract
            subseg=seg.extract(x0,x1,y0,y1)
            subimg=img.extract(x0,x1,y0,y1)


            
            # put the segID in the header
            subseg['SEGID']=segid
            
            # create the source
            self[segid]=Source(subimg,subseg,detzpt,segid=segid,\
                               filtsig=self.keyword('FILTSIG',seg,conf),
                               eroderad=self.keyword('ERODERAD',seg,conf),
                               maglim=conf['maglim'],minpix=conf['minpix'])
                               
            
            # update the progress bar
            #pb.increment()
            pb.update()

    def fromMEF(self,conf,seglist,imglist):
        ''' load sources via a multi-extension fits file '''

        print('[info]Loading sources from MEF segmentation map')
        
        # get a progress bar
        #pb=progressbar.ProgressBar(len(seglist))
        pb=tqdm.tqdm(total=len(seglist),dynamic_ncols=True,desc='MEF Segmap')
        
        detzpt=self.obsdata.detZeropoint
        for seghdu,imghdu in zip(seglist,imglist):
            segid=seghdu.header['SEGID']
            
            # set the prefix
            #pb.prefix=self.PREFIX.format(segid)
            pb.desc=self.PREFIX.format(segid)
            
            # read the images
            seg=FITSImage(seglist,seghdu)
            img=FITSImage(imglist,imghdu)
            
            src=Source(img,seg,detzpt,
                       lamb0=self.keyword('LAMB0',seg,conf),
                       lamb1=self.keyword('LAMB1',seg,conf),
                       dlamb=self.keyword('DLAMB',seg,conf),
                       filtsig=self.keyword('FILTSIG',seg,conf),
                       eroderad=self.keyword('ERODERAD',seg,conf),
                       maglim=conf['maglim'],minpix=conf['minpix'])
            self[src.segid]=src

            # increment
            #pb.increment()
            pb.update()
                

    
