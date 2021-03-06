import os
import numpy as np

from ... import h5table
from ...utilities import Pool

class Tabulate(object):
    DX=np.array([0,0,1,1],dtype=np.float)
    DY=np.array([0,1,1,0],dtype=np.float)

    def __init__(self,ttype,path='tables',nsub=10,remake=True,ncpu=None):
        # set the path for where the tables will be stored
        self.path=path
        if not os.path.isdir(self.path):
            os.mkdir(self.path)

        self.ttype=ttype.lower()

        print('[debug]Figure out if remake works right')
        
        # determine the subsampling frequency 
        if not isinstance(nsub,int):
            nsub=int(nsub)
            print('[warn]Nsub should be an integer')
        if nsub < 1:
            nsub=1
            print("[warn]Nsub should probably be >{}".format(nsub))
        self.nsub=nsub

        # set the flag to remake things
        self.remake=remake

        # record the CPU usage
        self.ncpu=ncpu

    

    def make_pdts(self,src,wav,beamconf,device,pixfrac=1.0):
        dwav=wav[1]-wav[0]    # compute bandwidth
        
        # make a table to write to
        #odt=h5table.ODT(src.name,beamconf.beam,wav)

        pdts=[]
        
        # compute ratio of pixel area between the FLT and the source
        pixrat=device.pixelarea/(pixfrac*src.pixelarea)

        # process each pixel in the source
        for xd,yd,wd in src:
                        
            # convert the corners of the direct image to the
            # corresponding grism image
            xg,yg=src.xy2xy(xd+self.DX,yd+self.DY,device)

            # drizzle these corners
            x,y,l,v=beamconf.drizzle(xg,yg,wav,pixfrac=pixfrac)
            
            if len(x)!=0:
                # define the pixel coordinate
                pix=(int(xd-src.ltv[0]),int(yd-src.ltv[1]))
                
                # scale the value, which at this time is
                # only accounting for the relative pixel area
                # 1. direct image weight (wd),
                # 2. ratio of pixel areas between seg & FLT
                # 3. wavelength sampling (trapezoidal rule)
                #v*=(pixrat*dwav)
                
                # create the table
                pdt=h5table.PDT(pix,x,y,l,v*pixrat*dwav)
                #,lamb0=wav[0],lamb1=wav[1],dlamb=dwav)
                                          
                # save to the table
                #pdts.extend(pdt)
                pdts.append(pdt)
        return pdts

    def make_omts(self,src,wav,beamconf,device,pixfrac=1.):

        # compute the edges of the source
        xd,yd=src.convex_hull()

        # change coordinates
        xg,yg=src.xy2xy(xd,yd,device)

        # disperse those pixels
        x,y,l,v=beamconf.drizzle(xg,yg,wav,pixfrac=pixfrac)


        # record as an OMT
        omt=h5table.OMT(src.name,beamconf.beam)
        #xy=[]

        if len(x)!=0:
            # select fractional to disperse
            #g=np.where(v > 
            #x,y=x[g],y[g]
            
            # compute unique x,y pairs
            pix=set(zip(x,y))
            x,y=list(zip(*pix))

            # update the table
            omt.extend(x,y)
            
        return [omt]

    
    def make_table(self,grism,sources,beam):
        pixfrac=1.0    # DO NOT CHANGE THIS VALUE
        dataset=grism.dataset

        ttype=self.ttype.lower()
        if ttype=='pdt':
            tabfunc=self.make_pdts
        elif ttype=='omt':
            tabfunc=self.make_omts
        else:
            print('[warn]The table type does not exist.')
            return

        with h5table.H5Table(dataset,path=self.path) as h5:
            tabname=h5.filename

            # process each device in the grism image
            for device in grism:
                

                # figure out which sourcs to do
                #if self.remake:
                #    sources_done=[]
                #else:
                #    sources_done=list(device.keys())

                    
                # load the config file
                beamconf=device.load_beam(beam)

                                
                # get the center of the device
                xc,yc=device.naxis1/2.,device.naxis2/2.

                # get the ODT wavelenegths.  NOTE: This are *NOT* the
                # same as the extraction wavelengths due to NSUB.
                # here using center of device.  Could improve this by
                # putting inside loop on sources and take (xc,yc)
                # from the source.  This is just faster and doesn't
                # seem to be a problem just yet
                #wav=beamconf.wavelengths(xc,yc,self.nsub)  
                #dwav=wav[1]-wav[0]

                # ok, now try using the default values of the extraction
                # from the XML file.
                dwav=device.defaults['dlamb']
                wav=np.arange(device.defaults['lamb0'],
                              device.defaults['lamb1']+dwav,dwav)



                
                # add some stuff ot the table
                #devtab.add_attribute('nsource',np.uint32(len(sources)))
                #devtab.add_attribute('wav0',np.float32(wav[0]))
                #devtab.add_attribute('wav1',np.float32(wav[-1]))
                #devtab.add_attribute('dwav',np.float32(dwav))


                # create a group for the device
                h5.add_device(device)

                # create beam for the data
                h5.add_beam(beam)

                # create a table-type for the data
                h5.add_ttype(self.ttype,wav0=wav[0],wav1=wav[-1],dwav=dwav)
                
                
                # ------ ABOVE IS GENERAL TABLE  -------
                # ------ BELOW IS FOR MAKING ODT -------


                # get the detector pixel area
                #devpix_area=device.pixelarea

               
                # process each source
                for src in sources:
                    #if src.name not in sources_done:  #

                    # make the table
                    #tab=self.make_odt(src,wav,beamconf,device)
                    tabs=tabfunc(src,wav,beamconf,device)
                    for tab in tabs:
                        h5.write_in_file(tab)
                        

                        
                        # compute the vertices in an Object Vertices Table
                        #ovt=tab.compute_vertices()                        
                        #h5.write_in_file(ovt)
                        
        return tabname

    def run(self,grisms,sources,beam):
        # create a pool
        pool=Pool(self.make_table,ncpu=self.ncpu,desc="Making tables")

        # run the pool
        #names=pool(grisms.values(),sources,beam)

        # for debugging
        tabnames=[self.make_table(grism,sources,beam) for grism in grisms]
                
        return tabnames
    
