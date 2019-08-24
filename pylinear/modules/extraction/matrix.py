import numpy as np
import timeit
import scipy.sparse.linalg as ssl
from scipy.sparse import coo_matrix
import pdb,sys

from . import lcurve,lsqrresult
from pylinear import h5table
from pylinear.utilities import progressbar,indices
from .fluxunit import FLUXSCALE

class Matrix(object):
    TTYPE='DDT'            # Which type of table to 
    def __init__(self,conf,grisms,sources,extconf,mskconf,grismFF):

        # dimensionalities
        self.nimg=len(grisms)
        self.nsrc=len(sources)

        # print a message
        msg="[info]Building the matrix: {} images, {} sources"
        print(msg.format(self.nimg,self.nsrc))
        
        # stuff for LSQR
        lsqrconf=conf['lsqr']
        self.atol=float(lsqrconf['atol'])
        self.btol=float(lsqrconf['btol'])
        self.conlim=float(lsqrconf['conlim'])
        self.maxiter=lsqrconf['maxiter']
        self.show=False
        
        # double check the type of maxiter
        if self.maxiter is not None:
            self.maxiter=int(self.maxiter)
            
        # get extraction properties for the sources
        nwav=[]
        for segid,src in sources:
            if src.lamb0 is None: src.lamb0=self.epar(conf,extconf,'lamb0')
            if src.lamb1 is None: src.lamb1=self.epar(conf,extconf,'lamb1')
            if src.dlamb is None: src.dlamb=self.epar(conf,extconf,'dlamb')
            nwav.append(src.nwav)
            
        # get cumulative indices
        cwav=np.cumsum(nwav)
        self.npar=cwav[-1]
        self.cwav=np.array([0,*cwav])

        # data to hold matrix/vector stuff
        ii,jj,aij=[],[],[]
        self.bi=[]


        # this was like 'i' before.  but now we need to increment for
        # each FLT and detector
        self.imgindex=0

        # just a short hand
        path=conf['tables']['path']
        
        # loop over images
        pb=progressbar.ProgressBar(self.nimg,prefix=' Loading ODTs')

        # output values
        i,j,aij=[],[],[]
        
        for fltindex,(fltfile,flt) in enumerate(grisms):
            # update the prograssbar
            pb.suffix='{}/{}'.format(fltindex+1,self.nimg)
            pb.increment()

            # do one FLT:            
            data=self.loadFLT(flt,sources,extconf,mskconf,grismFF,pb,path)

            # update the results
            i.extend(data[0])
            j.extend(data[1])
            aij.extend(data[2])

        
        if len(i)==0:
            print('[alarm]Matrix has no elements.')
            #raise RuntimeError("matrix had no elements")
            return

        print('SIZE OF i,j,aij',sys.getsizeof(i),\
              sys.getsizeof(j),sys.getsizeof(aij))
        
        # loaded everything
        print("[info]Compressing the indices")
        ic,iu=indices.compress(i)
        jc,ju=indices.compress(j)
        dim=np.array([len(iu),len(ju)])
        #self.npar=np.amax(jc)     # IDL has +1 here
        #self.npar=np.amax(jc)+1
        self.npar=np.amax(ju)+1
        del i,j



        
        # compute some things for ragged arrays
        if len(sources)==1:
            #srcind=np.zeros(self.npar+1,dtype=int)
            srcind=np.zeros(self.npar,dtype=int)
        else:
            srcind=np.digitize(ju,self.cwav)-1
        lam=ju-self.cwav[srcind]
        self.lam=lam.astype(int)
        
        # get the reverse indices
        segids=np.array(list(sources.keys()))
        self.ri=indices.reverse(segids[srcind])
        self.hsrc=np.bincount(srcind)

        # recast somethings
        aij=np.array(aij)
        
        # compute the frobenius norm
        self.frob=np.sqrt(np.sum(aij*aij))
        
        # sparse matrix is constructed as (ic,jc,np.array(mat['aij']),dim)
        self.A=ssl.aslinearoperator(coo_matrix((aij,(ic,jc)),shape=dim))
        del aij
        
        # record stuff
        self.bi=np.array(self.bi)
        self.icomp=ic
        self.iuniq=iu
        self.jcomp=jc
        self.juniq=ju


        # for making a plot
        self.lcurve=lcurve.LCurve(self.frob)


        
    def epar(self,conf,extconf,key):
        val=conf[key]
        if val is None:
            return getattr(extconf,key)
        else:
            return val

        
    def __imul__(self,v):
        self.A.A.data*=v
        self.frob*=v
        self.lcurve.frob*=v
        return self
    
        
    def loadFLT(self,flt,sources,extconf,mskconf,grismFF,pb,path):

        # output stuff
        i,j,aij=[],[],[]
        
        # make mask for this FLT
        masks=self.maskBeams(flt,mskconf,path)
        
        # open the H5Table
        with h5table.H5Table(flt.dataset,self.TTYPE,path=path) as h5:

            # loop over detectors
            for detname,detimg in flt:
                h5det=h5[detname]              # get the group
                detconf=extconf[detname]     # grism config

                # save this for easy access later
                self.npix=detimg.npix
                
                # read the images
                sci,scihdr=flt.readfits(detconf.sciext,detconf.extver)
                unc,unchdr=flt.readfits(detconf.uncext,detconf.extver)
                dqa,dqahdr=flt.readfits(detconf.dqaext,detconf.extver)
                xyg=[]         # a container

                # make a good pixel mask
                gpx=(dqa == 0) & (unc > 0)
                if len(masks)!=0: gpx &= masks[detname]
                del dqa,dqahdr        # don't need these anymore

                # call a load beam
                data=self.loadBeams(h5det,detconf,detimg,unc,gpx,sources,\
                                    grismFF)
                self.imgindex+=1

                # collect previous outputs (move this inside the if below)
                i.extend(data[0])
                j.extend(data[1])
                aij.extend(data[2])

                # collect the bi
                if len(data[3])!=0:
                    xyg=indices.unique(np.array(data[3]))
                    xg,yg=indices.one2two(xyg,detimg.naxis)
                    xg=xg.astype(int)
                    yg=yg.astype(int)
                    bi=sci[yg,xg]/unc[yg,xg]

                    # check for bad values in bi
                    g=np.where(np.isinf(bi))[0]
                    if len(g)!=0:
                        print('[warn]Infinite values in bi')
                        print(bi[g])
                        q=input()

                    # like IDL's push
                    self.bi.extend(bi)

                # save the memory usage
                del data

        return i,j,aij
                
    def maskBeams(self,flt,mskconf,path):

        masks={}
        if len(mskconf.beams)!=0:
            print("[info]Making beam mask for: {}".format(flt.filename))
            with h5table.H5Table(flt.dataset,path=path,suffix='omt') as h5:
                
                # loop over detectors
                for detname,detimg in flt:
                    h5det=h5[detname]              # get the group
                    detconf=mskconf[detname]       # grism config
                    mask=np.ones(detimg.naxis,dtype=np.bool)
                    for beam,beamconf in detconf:

                        h5beam=h5det[beam]
                        for segid in h5beam:
                            xyg=h5beam[segid][:]
                            xg,yg=indices.one2two(xyg,detimg.naxis)
                            mask[yg,xg]=False
                    masks[detname]=mask
        return masks
    
    @property
    def segids(self):
        segids=[ri[0] for ri in self.ri]
        return segids
                
    def loadBeams(self,h5det,detconf,detimg,unc,gpx,sources,grismFF,thresh=0.0):
        thresh=np.float64(thresh)
        
        # output stuff
        i,j,aij,xyg=[],[],[],[]
        
        
        # loop over beams in question
        for beam,beamconf in detconf:
            h5beam=h5det[beam]
            
            # loop over the sources
            for srcindex,(segid,src) in enumerate(sources):

                if self.TTYPE=='ODT':                 # Read the ODT
                    odt=h5table.ODT(src.segid)
                    odt.readH5(h5beam)
                    ddt=odt.decimate()
                    del(odt)
                elif self.TTYPE=='DDT':               # Read the DDT
                    ddt=h5table.DDT(src.segid)
                    ddt.readH5(h5beam)
                else:
                    msg="Invalid Table Type: {}".format(self.TTYPE)
                    raise NotImplementedError(msg)

                if len(ddt)!=0:
                    
                    # get limits 
                    limits=src.limits
                    wav0=np.amin(limits)
                    wav1=np.amax(limits)
                    
                    # remove pixels out of range and/or in GPX
                    xg,yg=indices.one2two(ddt.xyg,detimg.naxis)
                    g=np.where((ddt.wav >=wav0) & (ddt.wav<=wav1) & \
                               (gpx[yg,xg]) & (ddt.val>thresh))[0]
                    if len(g)!=0:
                        ddt.select(g)
                        xg,yg=xg[g],yg[g]
                        del g
                        
                        # compute (x,y) for each value
                        #xg,yg=indices.one2two(ddt.xyg,detimg.naxis)
                        
                        # compute the scaling terms
                        ff=grismFF(xg,yg,ddt.wav,detconf.detector)
                        pa=detimg.pixelArea(xg,yg)    # pixel area map
                        sens=beamconf.sensitivity(ddt.wav)*FLUXSCALE

                        # scale the DDT
                        ddt*=(ff*pa*sens)
                        del ff,pa,sens
                                                
                        # compute the wavelength indices
                        lamind=np.digitize(ddt.wav,limits)-1
                        
                        # scale the matrix elements by uncer
                        val=ddt.val/unc[yg,xg]
                        
                        # compute the matrix element
                        iii=ddt.xyg.astype(np.uint64)+\
                             self.imgindex*detimg.npix
                        jjj=lamind+self.cwav[srcindex]
                        ij=jjj+self.npar*iii
                        ij=ij.astype(np.uint64)
                        del iii,jjj
                        
                        # decimate over repeated indices
                        aiju,iju=indices.decimate(ij,val)
                        
                        # compute matrix coordinates
                        iu,ju=np.divmod(iju,self.npar)

                        # compute pixel positions
                        imgind,xygind=np.divmod(iu,detimg.npix)
                        #imgind=indices.unique(imgind)   # this is not needed
                        xygind=indices.unique(xygind)

                        # save the outputs
                        i.extend(list(iu))
                        j.extend(list(ju))
                        aij.extend(list(aiju))
                        xyg.extend(list(xygind))

        return i,j,aij,xyg
                        
        
                
    def residualMatrix(self,j,resid):
        g=np.where((self.A.A.col == j))[0]

        ii=self.A.A.row[g]
        jj=self.A.A.col[g]
        aij=self.A.A.data[g]
        iic,iiu=indices.compress(ii)
        jjc,jju=indices.compress(jj)
 
        dim=np.array([max(iic),max(jjc)])+1

        
        A=ssl.aslinearoperator(coo_matrix((aij,(iic,jjc)),shape=dim))
        bi=resid[ii]
            
        return A,bi


    
    def runLSQR(self,logdamp,atol=None,btol=None,conlim=None,show=None,x0=None):

        if show is None: show=self.show
        if atol is None: atol=self.atol
        if btol is None: btol=self.btol
        if conlim is None: conlim=self.conlim
        
        logfrob=np.log10(self.frob)
        
        # force this to be a list
        if np.isscalar(logdamp):
            logdamp=[logdamp]

        # collect the outputs
        out=[]

        # iterate over logdamp... could Multiprocess this
        for ldamp in logdamp:
            t1=timeit.default_timer()
            if ldamp is None:
                damp=0.
            else:
                damp=np.power(10.,ldamp)*self.frob


                
                
            # run LSQR
            print("[info]Starting LSQR log(l) = {0:+.3f}".format(ldamp))
            
            '''
            # Using SciPy the way I think it works:
            r=ssl.lsqr(self.A,self.bi,damp=damp,x0=x0,show=show,calc_var=True,\
                       atol=atol,btol=btol,conlim=conlim,iter_lim=self.maxiter)


            '''
            
            # Using LSQR a la the IDL implementation
            if x0 is None:
                bi=self.bi
            else:
                bi=self.bi-self.A.matvec(x0)
            
            r=ssl.lsqr(self.A,bi,damp=damp,show=show,calc_var=True,\
                       atol=atol,btol=btol,conlim=conlim,iter_lim=self.maxiter)
            if x0 is not None:
                r=(r[0]+x0,*r[1:])


            # there doesn't seem to be any difference whatsoever.
                

            # get the final time
            t2=timeit.default_timer()
                
            # package the output
            r=lsqrresult.LSQRResult(*r,damp/self.frob,t2-t1)

            
            # update the plot
            self.lcurve.append(r.r1norm,r.xnorm,r.logdamp)

            # save the result
            out.append(r)
            
        if len(out)==1:
            out=out[0]


            
        return out

    


    @property
    def shape(self):
        try:
            sh=self.A.shape
        except:
            sh=[None,None]
        return sh
        
    @property
    def norm(self):
        try:
            nrm=self.frob
        except:
            nrm=None
        return nrm
