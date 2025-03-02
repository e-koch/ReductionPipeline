
import sys
import os
from glob import glob
import shutil
import traceback
import numpy as np

# Additional QA plotting routines
from lband_pipeline.qa_plotting import (make_qa_scan_figures,
                                        make_qa_tables,
                                        run_all_uvstats,
                                        make_all_caltable_txt,
                                        make_all_flagsummary_data)

# Info for SPW setup
from lband_pipeline.spw_setup import (create_spw_dict, linerest_dict_GHz,
                                      continuum_spws_with_hi)
from lband_pipeline.read_config_files import read_calibrator_absorption_cfg

# Will read from the filename defined in `config_files/master_config.cfg`
calibrator_line_range_kms = read_calibrator_absorption_cfg(filename=None)

# Flag HI absorption on the calibrators.
from lband_pipeline.line_tools import flag_hi_foreground

from lband_pipeline.target_setup import (identify_target)

# Handle runs where the internet query to the baseline correction site will
# fail
from lband_pipeline.offline_antposn_corrections import make_offline_antpos_table

from lband_pipeline.flagging_tools import flag_quack_integrations

from lband_pipeline.quicklook_imaging import quicklook_continuum_imaging

from lband_pipeline.ms_split_tools import split_ms_final_all

# Check that DISPLAY is set. Otherwise, force an error
# We need DISPLAY set for plotms to export png or txt files.
if os.getenv('DISPLAY') is None:
    raise ValueError("DISPLAY is not set. Try using xvfb for remote systems.")

# Unset LD_LIBRARY_PATH. CASA isn't supposed to be using it anymore
os.environ['LD_LIBRARY_PATH'] = ""

# Read in to skip a refant if needed.
refant_ignore_filename = 'refant_ignore.txt'
if os.path.exists(refant_ignore_filename):
    with open(refant_ignore_filename, 'r') as file:
        refantignore = file.read().replace('\n', '')
else:
    refantignore = ""

mySDM = sys.argv[-1]
myvis = mySDM if mySDM.endswith("ms") else mySDM + ".ms"

# Tracks should follow the VLA format, starting with the project code
# e.g. 14B-088.sbXX.ebXX.mjd
proj_code = mySDM.split(".")[0]

# Get the SPW mapping for the continuum MS.
spwdict_filename = "spw_definitions.npy"
contspw_dict = create_spw_dict(myvis, save_spwdict=True,
                               spwdict_filename=spwdict_filename)

# Get SPWs that contain the HI line
spws_with_hi = continuum_spws_with_hi(contspw_dict)

# Identify which of our targets are observed.
# NOTE: Assumes that we only look at ONE galaxy per MS right now.
# This will break if more than one galaxy is observed in a single track.
# NOTE: the target name must be specified in "target_setup.py"
thisgal = identify_target(myvis)

products_folder = "products"

__rethrow_casa_exceptions = True

# Check if there's an existing pipeline run. If so, check status to
# restart at last position:
context_files = glob("pipeline*.context")
if len(context_files) > 0:

    # Will open the most recent context file
    context = h_resume()

    casalog.post("Restarting from context {}".format(context))


    # Get pipeline call order:
    callorder = ['hifv_importdata',
                 'hifv_hanning',
                 'hifv_flagdata',
                 'hifv_vlasetjy',
                 'hifv_priorcals',
                 'hifv_syspower',
                 'hifv_testBPdcals',
                 'hifv_checkflag',
                 'hifv_semiFinalBPdcals',
                 'hifv_checkflag',
                 'hifv_solint',
                 'hifv_fluxboot',
                 'hifv_finalcals',
                 'hifv_applycals',
                 'hifv_checkflag',
                 'hifv_statwt',
                 'hifv_plotsummary',
                 'hif_makeimlist',
                 'hif_makeimages',
                 'hifv_exportdata']

    # Get existing order to match with the call order:
    current_callorder = [result.read().taskname for result in context.results]

    # Make sure the order is what we expect
    matching_calls = np.array(current_callorder) == np.array(callorder[:len(current_callorder)])

    if not matching_calls.all():
        raise ValueError("Call order not expected for this script: Expected: {0}\nFound: {1}"
                         .format(callorder[:len(current_callorder)], current_callorder))

    # Do we just need to make additional QA plots?
    # i.e. the calibration did finish
    if len(current_callorder) == len(callorder):
        skip_pipeline = True

        restart_stage = len(callorder) + 1

        casalog.post("Calibration pipeline completed. Running QA plots only.")


    # Otherwise start from the next stage
    else:
        skip_pipeline = False

        # Start from the next stage of what was last completed
        restart_stage = len(current_callorder)

        casalog.post("Restarting at stage: {0} {1}".format(restart_stage, callorder[restart_stage]))


# Otherwise this is a fresh run:
else:

    casalog.post("No context file found. Starting new pipeline run.")

    context = h_init()

    restart_stage = 0

    skip_pipeline = False

context.set_state('ProjectSummary', 'observatory',
                  'Karl G. Jansky Very Large Array')
context.set_state('ProjectSummary', 'telescope', 'EVLA')
context.set_state('ProjectSummary', 'proposal_code', proj_code)

if not skip_pipeline:

    try:

        if restart_stage == 0:
            hifv_importdata(vis=mySDM,
                            createmms='automatic',
                            asis='Receiver CalAtmosphere',
                            ocorr_mode='co',
                            nocopy=False,
                            overwrite=False)

        # TODO: introduce flag for re-runs to avoid smoothing again
        # ONLY run if we're starting the first reduction to avoid
        if restart_stage <= 1:
            hifv_hanning(pipelinemode="automatic")
            h_save()

        if restart_stage <= 2:

            for thisspw in spws_with_hi:
                flag_hi_foreground(myvis,
                                   calibrator_line_range_kms,
                                   thisspw,
                                   cal_intents=["CALIBRATE*"],
                                   test_run=False,
                                   test_print=True)

            # Add additional quacking to the beginning of scans.
            flag_quack_integrations(myvis, num_ints=3.0)

            hifv_flagdata(flagbackup=False,
                          scan=True,
                          fracspw=0.01,
                          intents='*POINTING*,*FOCUS*,*ATMOSPHERE*,*SIDEBAND_RATIO*,*UNKNOWN*,*SYSTEM_CONFIGURATION*,  *UNSPECIFIED#UNSPECIFIED*',
                          clip=True,
                          baseband=True,
                          shadow=True,
                          quack=True,
                          edgespw=True,
                          autocorr=True,
                          hm_tbuff='1.5int',
                          tbuff=0.0,
                          template=True,
                          filetemplate="manual_flagging.txt",
                          online=True)
            h_save()

        if restart_stage <= 3:
            hifv_vlasetjy(pipelinemode="automatic")

        if restart_stage <= 4:
            # Remove existing iono correction images if they exist.
            os.system("rm -r iono.*.im")
            hifv_priorcals(pipelinemode="automatic")
            h_save()

            # Check offline tables (updated before each run) for antenna corrections
            # If the online tables were accessed and the correction table already exists,
            # skip remaking.
            make_offline_antpos_table(myvis,
                                     data_folder="VLA_antcorr_tables",
                                     skip_existing=True)

        if restart_stage <= 5:
            hifv_syspower(pipelinemode="automatic",
                          apply=True)

        if restart_stage <= 6:
            hifv_testBPdcals(pipelinemode="automatic",
                             weakbp=False,
                             refantignore=refantignore,
                             doflagundernspwlimit=True)

        if restart_stage <= 7:
            hifv_checkflag(checkflagmode='bpd-vla')
            h_save()

        if restart_stage <= 8:
            hifv_semiFinalBPdcals(pipelinemode="automatic",
                                  weakbp=False,
                                  refantignore=refantignore)

        if restart_stage <= 9:
            hifv_checkflag(checkflagmode='allcals-vla')
            h_save()

        if restart_stage <= 10:
            hifv_solint(pipelinemode="automatic",
                        refantignore=refantignore)

        if restart_stage <= 11:
            hifv_fluxboot(pipelinemode="automatic",
                          fitorder=2,
                          refantignore=refantignore)
            h_save()

        if restart_stage <= 12:
            # Don't grow flags at this step. We have long slews to our pol cals
            # and growtime=50 can wipe out the whole scan!
            # flagdata(vis=myvis, mode='extend', extendpols=True, action='apply',
            #          display='', flagbackup=False, intent='*CALIBRATE*',
            #          growtime=99.9, growfreq=99.9)
            # flagdata(vis=myvis, mode='extend', growtime=90.0, growfreq=90.0, extendpols=False,
            #          action='apply', display='', flagbackup=False, intent='*CALIBRATE*',
            #          growaround=True, flagneartime=True, flagnearfreq=True)

            hifv_finalcals(pipelinemode="automatic",
                           weakbp=False,
                           refantignore=refantignore)

        if restart_stage <= 13:
            hifv_applycals(pipelinemode="automatic",
                           flagdetailedsum=True,
                           gainmap=False,
                           flagbackup=True,
                           flagsum=True)
            h_save()

        if restart_stage <= 14:
            hifv_checkflag(checkflagmode='target-vla')
            h_save()

        # if restart_stage <= 14:
        #     hifv_targetflag(intents='*TARGET*')
        #     h_save()

        if restart_stage <= 15:
            hifv_statwt(datacolumn='corrected')
            h_save()

        if restart_stage <= 16:
            hifv_plotsummary(pipelinemode="automatic")

        if restart_stage <= 17:
            hif_makeimlist(nchan=-1,
                           calcsb=False,
                           intent='PHASE,BANDPASS',
                           robust=-999.0,
                           parallel='automatic',
                           per_eb=False,
                           calmaxpix=300,
                           specmode='cont',
                           clearlist=True)

        if restart_stage <= 18:

            hif_makeimages(hm_masking='centralregion')
            h_save()

        if restart_stage <= 19:
            # Make a folder of products for restoring the pipeline solution
            if not os.path.exists(products_folder):
                os.mkdir(products_folder + '/')

            hifv_exportdata(products_dir=products_folder + '/',
                            gainmap=False,
                            exportmses=False,
                            exportcalprods=True)

    except Exception as ex:
        casalog.post("Encountered exception: {}".format(ex))

        casalog.post("Traceback: {}".format(traceback.print_exc()))

        h_save()

        print("Encountered exception: {}. Exiting with error code 1".format(ex))

        sys.exit(1)

    finally:

        h_save()

# Make a new directory for the imaging outputs
# Not required. I just like cleaning up the folder a bit.
if not os.path.exists("image_outputs"):
    os.mkdir("image_outputs")

image_files = glob("oussid*")

for fil in image_files:
    shutil.move(fil, f"image_outputs/{fil}")

# Copy the SPW dictionary file into products
if os.path.exists(spwdict_filename):
    os.system(f"cp {spwdict_filename} products/")

# --------------------------------
# Split the calibrated column out into target and calibrator parts.
# --------------------------------
split_ms_final_all(myvis,
                   contspw_dict,
                   data_column='CORRECTED',
                   target_name_prefix="",
                   time_bin='0s',
                   keep_flags=True,
                   overwrite=False)

# --------------------------------
# Make quicklook images of targets
# --------------------------------
run_quicklook = True

# Run dirty imaging only for a quicklook
if run_quicklook:
    # NOTE: We will attempt a very light clean as it can really highlight
    # which SPWs have significant RFI.
    # TODO: Need to check how much added time this results in for A/B config.
    quicklook_continuum_imaging(myvis, contspw_dict,
                                niter=0, nsigma=5.)

    os.system("cp -r {0} {1}".format('quicklook_imaging', products_folder))

# ----------------------------
# Now make additional QA plots:
# -----------------------------

# Hard-code in making txt files
text_output = True

if text_output:
    # make_bandpass_txt(myvis, output_folder='finalBPcal_txt')

    make_all_caltable_txt(myvis)

    make_qa_tables(myvis,
                   output_folder='scan_plots_txt',
                   outtype='txt',
                   overwrite=False,
                   chanavg=4096,)

    # make_all_flagsummary_data(myvis, output_folder='perfield_flagfraction_txt')

    # Move these folders to the products folder.
    os.system("cp -r {0} {1}".format('final_caltable_txt', products_folder))
    os.system("cp -r {0} {1}".format('scan_plots_txt', products_folder))
    # os.system("cp -r {0} {1}".format('perfield_flagfraction_txt', products_folder))

else:

    # make_spw_bandpass_plots(myvis,
    #                         bp_folder="finalBPcal_plots",
    #                         outtype='png')

    make_qa_scan_figures(myvis,
                         output_folder='scan_plots',
                         outtype='png')

    # Move these folders to the products folder.
    # os.system("cp -r {0} {1}".format('finalBPcal_plots', products_folder))
    os.system("cp -r {0} {1}".format('scan_plots', products_folder))

# Make detailed uvresid plots.
# These are to check if any calibrators have source structure not accounted for.
# In that case, a flux.csv file needs to be provided for a subsequent pipeline run

uvresid_path = "uvresid_plots"

# Not being used right now. The LGLBS gain cals are well-modeled as pt. sources
do_uvstats = False

# Skip re-run if the folder already exists:
if do_uvstats:
    if not os.path.exists(uvresid_path):

        run_all_uvstats(myvis, uvresid_path,
                        uv_threshold=3, uv_nsigma=3,
                        try_phase_selfcal=True,
                        cleanup_calsplit=True,
                        cleanup_phaseselfcal=True)

        # We're cleaning up the other data products to make these plots.
        # So just copy the whole folder over.
        os.system("cp -r {0} {1}".format(uvresid_path, products_folder))

    else:
        casalog.post("Found existing uvresidual checks. Skipping.")
