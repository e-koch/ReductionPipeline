
import os
import datetime

from casatasks import tclean, rmtables, exportfits

from casatools import logsink
from casatools import ms
from casatools import imager
from casatools import synthesisutils
from casatools import msmetadata

casalog = logsink()

from lband_pipeline.spw_setup import linerest_dict_GHz

from lband_pipeline.target_setup import (target_line_range_kms,
                                         target_vsys_kms)


def cleanup_misc_quicklook(filename, remove_residual=True,
                           remove_psf=True,
                           remove_image=False):
    '''
    Reduce number of files that aren't needed for QA.
    '''

    rmtables(f"{filename}.model")
    rmtables(f"{filename}.sumwt")
    rmtables(f"{filename}.pb")
    rmtables(f"{filename}.mask")

    if remove_residual:
        rmtables(f"{filename}.residual")

    if remove_psf:
        rmtables(f"{filename}.psf")

    if remove_image:
        rmtables(f"{filename}.image")


def quicklook_line_imaging(myvis, thisgal, linespw_dict, channel_width_kms=20.,
                           niter=0, nsigma=5., imsize_max=800,
                           overwrite_imaging=False,
                           export_fits=True):

    if not os.path.exists("quicklook_imaging"):
        os.mkdir("quicklook_imaging")

    this_vsys = target_vsys_kms[thisgal]

    # Pick our line range based on the HI for all lines.
    this_velrange = target_line_range_kms[thisgal]['HI']
    # We have a MW foreground window on some targets. Skip this for the galaxy range.
    if isinstance(this_velrange[0], list):
        for this_range in this_velrange:
            if this_vsys > this_range[1] and this_vsys < this_range[0]:
                this_velrange = this_range
                break


    width_vel = channel_width_kms
    width_vel_str = f"{width_vel}km/s"

    start_vel = f"{int(min(this_velrange))}km/s"
    nchan_vel = int(abs(this_velrange[0] - this_velrange[1]) / width_vel)

    # Select only the non-continuum SPWs
    line_spws = []
    for thisspw in linespw_dict:
        if "continuum" not in linespw_dict[thisspw]['label']:
            # Our 20A-346 tracks have a combined OH1665/1667 SPW. Split into separate cubes in this case
            line_labels = linespw_dict[thisspw]['label'].split("-")

            for line_label in line_labels:
                line_spws.append([str(thisspw), line_label])

    # Select our target fields. We will loop through
    # to avoid the time + memory needed for mosaics.

    synthutil = synthesisutils()

    myms = ms()

    # if no fields are provided use observe_target intent
    # I saw once a calibrator also has this intent so check carefully
    # mymsmd.open(vis)
    myms.open(myvis)

    mymsmd = myms.metadata()

    target_fields = mymsmd.fieldsforintent("*TARGET*", True)

    mymsmd.close()
    myms.close()

    t0 = datetime.datetime.now()

    # Loop through targets and line SPWs
    for target_field in target_fields:

        casalog.post(f"Quick look imaging of field {target_field}")

        # Loop through the SPWs to identify the biggest image size needed.
        # For ease downstream, we will use the same imsize for all SPWs.
        # NOTE: for L-band, that's a factor of ~2 difference. It may be more pronounced in other
        # bands

        cell_size = {}
        imsizes = []

        for thisspw_info in line_spws:

            thisspw, line_name = thisspw_info

            # Ask for cellsize
            this_im = imager()
            this_im.selectvis(vis=myvis, field=target_field, spw=str(thisspw))

            image_settings = this_im.advise()
            this_im.close()

            # When all data is flagged, uvmax = 0 so cellsize = 0.
            # Check for that case to avoid tclean failures
            # if image_settings[2]['value'] == 0.:
            #     casalog.post(f"All data flagged for {this_imagename}. Skipping")
            #     continue

            # NOTE: Rounding will only be reasonable for arcsec units with our L-band setup.
            # Could easily fail on ~<0.1 arcsec cell sizes.
            cell_size[thisspw] = [image_settings[2]['value'], image_settings[2]['unit']]

            # No point in estimating image size for an empty SPW.
            if image_settings[2]['value'] == 0.:
                continue

            # For the image size, we will do an approx scaling was
            # theta_PB = 45 / nu (arcmin)
            this_msmd = msmetadata()
            this_msmd.open(myvis)
            mean_freq = this_msmd.chanfreqs(int(thisspw)).mean() / 1.e9 # Hz to GHz
            this_msmd.close()

            approx_pbsize = 1.2 * (45. / mean_freq) * 60 # arcsec
            approx_imsize = synthutil.getOptimumSize(int(approx_pbsize / image_settings[2]['value']))
            imsizes.append(approx_imsize)

        this_imsize = min(imsize_max, max(imsizes))

        for thisspw_info in line_spws:

            thisspw, line_name = thisspw_info

            casalog.post(f"Quick look imaging of field {target_field} SPW {thisspw}")

            this_imagename = f"quicklook_imaging/quicklook-{target_field}-spw{thisspw}-{line_name}-{myvis}"

            if export_fits:
                check_exists = os.path.exists(f"{this_imagename}.image")
            else:
                check_exists = os.path.exists(f"{this_imagename}.image.fits")

            if check_exists:
                if overwrite_imaging:
                    rmtables(f"{this_imagename}*")
                else:
                    casalog.post(f"Found {this_imagename}. Skipping imaging.")
                    continue

            if cell_size[thisspw][0] == 0:
                casalog.post(f"All data flagged for {this_imagename}. Skipping")
                continue

            this_cellsize = f"{round(cell_size[thisspw][0] * 0.8, 1)}{cell_size[thisspw][1]}"

            this_pblim = 0.5

            this_nsigma = nsigma
            this_niter = niter

            # Clean up any possible imaging remnants first
            rmtables(f"{this_imagename}*")

            tclean(vis=myvis,
                   field=target_field,
                   spw=str(thisspw),
                   cell=this_cellsize,
                   imsize=this_imsize,
                   specmode='cube',
                   weighting='briggs',
                   robust=0.0,
                   start=start_vel,
                   width=width_vel_str,
                   nchan=nchan_vel,
                   niter=this_niter,
                   nsigma=this_nsigma,
                   imagename=this_imagename,
                   restfreq=f"{linerest_dict_GHz[line_name]}GHz",
                   pblimit=this_pblim)

            if export_fits:
                exportfits(imagename=f"{this_imagename}.image",
                           fitsimage=f"{this_imagename}.image.fits",
                           history=False,
                           overwrite=True)

            # Clean-up extra imaging products if they are not needed.
            cleanup_misc_quicklook(this_imagename, remove_psf=True,
                                    remove_residual=this_niter == 0,
                                    remove_image=True if export_fits else False)

    t1 = datetime.datetime.now()

    casalog.post(f"Quicklook line imaging took {t1 - t0}")


def quicklook_continuum_imaging(myvis, contspw_dict,
                                niter=0, nsigma=5., imsize_max=800,
                                overwrite_imaging=False,
                                export_fits=True):
    '''
    Per-SPW MFS, nterm=1, dirty images of the targets
    '''

    if not os.path.exists("quicklook_imaging"):
        os.mkdir("quicklook_imaging")


    # Select only the continuum SPWs (in case there are any line SPWs).
    continuum_spws = []
    for thisspw in contspw_dict:
        if "continuum" in contspw_dict[thisspw]['label']:
                continuum_spws.append(str(thisspw))

    # Select our target fields. We will loop through
    # to avoid the time + memory needed for mosaics.

    synthutil = synthesisutils()

    myms = ms()

    # if no fields are provided use observe_target intent
    # I saw once a calibrator also has this intent so check carefully
    # mymsmd.open(vis)
    myms.open(myvis)

    mymsmd = myms.metadata()

    target_fields = mymsmd.fieldsforintent("*TARGET*", True)

    mymsmd.close()
    myms.close()

    t0 = datetime.datetime.now()

    # Loop through targets and line SPWs
    for target_field in target_fields:

        casalog.post(f"Quick look imaging of field {target_field}")

        cell_size = {}
        imsizes = []

        for thisspw in continuum_spws:

            # Ask for cellsize
            this_im = imager()
            this_im.selectvis(vis=myvis, field=target_field, spw=str(thisspw))

            image_settings = this_im.advise()
            this_im.close()

            # When all data is flagged, uvmax = 0 so cellsize = 0.
            # Check for that case to avoid tclean failures
            # if image_settings[2]['value'] == 0.:
            #     casalog.post(f"All data flagged for {this_imagename}. Skipping")
            #     continue

            # NOTE: Rounding will only be reasonable for arcsec units with our L-band setup.
            # Could easily fail on ~<0.1 arcsec cell sizes.
            cell_size[thisspw] = [image_settings[2]['value'], image_settings[2]['unit']]

            # No point in estimating image size for an empty SPW.
            if image_settings[2]['value'] == 0.:
                continue

            # For the image size, we will do an approx scaling was
            # theta_PB = 45 / nu (arcmin)
            this_msmd = msmetadata()
            this_msmd.open(myvis)
            mean_freq = this_msmd.chanfreqs(int(thisspw)).mean() / 1.e9 # Hz to GHz
            this_msmd.close()

            approx_pbsize = 1.2 * (45. / mean_freq) * 60 # arcsec
            approx_imsize = synthutil.getOptimumSize(int(approx_pbsize / image_settings[2]['value']))
            imsizes.append(approx_imsize)

        this_imsize = min(imsize_max, max(imsizes))

        for thisspw in continuum_spws:

            casalog.post(f"Quick look imaging of field {target_field} SPW {thisspw}")

            this_imagename = f"quicklook_imaging/quicklook-{target_field}-spw{thisspw}-continuum-{myvis}"

            if export_fits:
                check_exists = os.path.exists(f"{this_imagename}.image")
            else:
                check_exists = os.path.exists(f"{this_imagename}.image.fits")

            if check_exists:
                if overwrite_imaging:
                    rmtables(f"{this_imagename}*")
                else:
                    casalog.post(f"Found {this_imagename}. Skipping imaging.")
                    continue

            if cell_size[thisspw][0] == 0:
                casalog.post(f"All data flagged for {this_imagename}. Skipping")
                continue

            this_cellsize = f"{round(cell_size[thisspw][0] * 0.8, 1)}{cell_size[thisspw][1]}"

            this_pblim = 0.5

            this_nsigma = nsigma
            this_niter = niter

            # Clean up any possible imaging remnants first
            rmtables(f"{this_imagename}*")

            tclean(vis=myvis,
                   field=target_field,
                   spw=str(thisspw),
                   cell=this_cellsize,
                   imsize=this_imsize,
                   specmode='mfs',
                   nterms=1,
                   weighting='briggs',
                   robust=0.0,
                   niter=this_niter,
                   nsigma=this_nsigma,
                   fastnoise=True,
                   imagename=this_imagename,
                   pblimit=this_pblim)

            if export_fits:
                exportfits(imagename=f"{this_imagename}.image",
                           fitsimage=f"{this_imagename}.image.fits",
                           history=False,
                           overwrite=True)

            # Clean-up extra imaging products if they are not needed.
            cleanup_misc_quicklook(this_imagename, remove_psf=True,
                                    remove_residual=this_niter == 0,
                                    remove_image=True if export_fits else False)

    t1 = datetime.datetime.now()

    casalog.post(f"Quicklook continuum imaging took {t1 - t0}")
