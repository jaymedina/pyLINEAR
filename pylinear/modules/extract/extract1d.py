from astropy.io import fits
from datetime import datetime
from timeit import default_timer

import os,pwd
from matplotlib.backends.backend_pdf import PdfPages

from ... import info
from ...config import Config
from .. import header_utils
from .residuals import Residuals
from .extract import Extract
from .group import make_groups

def extract1d(grisms,sources,beams,logdamp,method,fileroot,path,
              inverter='lsqr',mskbeams=None,group=True):
              
              

    # record the starting time
    t1=default_timer()    
    
    # specify some filenames
    x1dfile='{}_x1d.fits'.format(fileroot)
    pdffile='{}_lcv.pdf'.format(fileroot)


    # what force beams to be a list
    if not isinstance(beams,(tuple,list)):
        beams=[beams]

    
    
    # build the groups
    if group and (len(sources)>1):
        groups=make_groups(grisms,sources,beams,path)
    else:
        groups=[list(sources.keys())]
    ngrp=len(groups)
    
    # build an extraction object
    extract=Extract(inverter=inverter,method=method)

    # this will collect the outputs
    source_hdu={}
    group_hdu=[]

    # process each group
    with PdfPages(pdffile) as pdf:
        # put some stuff in the PDF
        d=pdf.infodict()
        d['Title']='L-Curve Results'
        d['Author']=pwd.getpwuid(os.getuid()).pw_gecos  #getpass.getuser()
        d['Subject']='L-Curve results for grouped data from pyLINEAR.'
        d['Keywords']='pylinear grism l-curve groups'
        d['Producer']=__name__


        
        # Nota Bene:
        # what I want to do here, is create a new instance of
        # SourceCollection with the same metadata, but a different
        # set of sources.  Ideally, this would be a method of
        # SourceCollection, where you pass it a set of SEGIDs and it
        # returns a new instance with those sources loaded.  I thought
        # copy.deepcopy() would work, but I coudn't figure this out.
        # Instead, what I do, is get all the sources out of the
        # collection instance, then put back sources as they're needed.
        # Then at the end, put all the sources back in in the same
        # order they were originally in.


        # make something for the residuals
        residuals=Residuals(grisms)
        
        # extract the sources for saving
        sources_dict={source.segid:source for source in sources}
        for group,segids in enumerate(groups):

            # dump the sources and put back in select objects
            sources.clear()
            for segid in segids:
                sources[segid]=sources_dict[segid]

            # build a matrix
            extract.build_matrix(grisms,sources,beams,path,mskbeams=mskbeams)
                
            # run the extraction method
            sres,gres=extract.run(logdamp,group=group,pdf=pdf,mcmc=False,
                                  residuals=residuals)
                                  
            # collect the results
            source_hdu.update(sres)
            group_hdu.append(gres)

        # finalize the residuals
        residuals.apply_uncertainty()
        residuals.gzip_files()

            
        # put all the sources back in
        sources.clear()
        for k,v in sources_dict.items():
            sources[k]=v
        
    # sort the results by SEGID
    source_hdu={k:v for k,v in sorted(source_hdu.items())}

    # compute the runtime
    t2=default_timer()
    dt=t2-t1
    days,rem=divmod(dt,24*60*60)
    hours,rem=divmod(rem,60*60)
    mins,secs=divmod(rem,60)
    times=(int(days),int(hours),int(mins),int(secs))
    runtime='{0}d{1:02d}h{2:02d}m{3:02d}s'.format(*times)
    
    # get a timestamp
    now=datetime.now()
    
    
    # make primary HDU
    phdu = fits.PrimaryHDU()

    header_utils.add_software_log(phdu.header)
    for after in phdu.header.keys():
        pass

    

    phdu.header.set('DETFILE',value=sources.obscat.detfile,after=after,
                    comment='image for detection weights')
    phdu.header.set('NGROUP',value=len(groups),after='DETFILE',
                    comment='number of groups')
    phdu.header.set('NGRISM',value=len(grisms),after='NGROUP',
                    comment='number of grism exposures')                    
    phdu.header.set('NSOURCE',value=len(sources),after='NGRISM',
                    comment='number of sources')
    #phdu.header.set('GRISM',value=grisms.grism[0],after='NSOURCE',
    #                comment='grism element')
    #phdu.header.set('BLOCKING',value=grisms.grism[1],after='GRISM',
    #                comment='Blocking filter')                    
    header_utils.add_stanza(phdu.header,'Observational Settings',before='DETFILE')
    
    # put the config into the header
    Config().update_header(phdu.header)
    
    # put some Comments into the file.
    header_utils.add_disclaimer(phdu.header)

    # oky... let's put the file together
    hdul=fits.HDUList()

    # the primary header
    hdul.append(phdu)

    # the sources
    for segid,hdu in source_hdu.items():
        hdul.append(hdu)

    # the groups
    for hdu in group_hdu:
        hdul.append(hdu)

    # write the file now...
    hdul.writeto(x1dfile,overwrite=True)

