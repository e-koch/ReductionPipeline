

'''
SPW setup info for LG tracks.

The goal is to:
1) identify line and continuum SPWs,
2) Label the line SPWs,
3) Keep some basic metadata on each SPW (nchan, bandwidth, etc.)

Currently only tested for 20A-346, 13A-213 (NGC6822 track).

'''

# Vsys for matching targets.
from lband_pipeline.target_setup import target_vsys_kms


from lband_pipeline.line_tools.line_flagging import lines_rest2obs

# This is all lines in L-band that we care about
# Most of the RRLs aren't observed, this is just complete
# so every choice is always available to match.
linerest_dict_GHz = {"HI": 1.420405752,
                     "OH1612": 1.612231,
                     "OH1665": 1.66540180,
                     "OH1667": 1.66735900,
                     "OH1720": 1.72053,
                     "H186a": 1.01376730,
                     "H185a": 1.03025116,
                     "H184a": 1.04709434,
                     "H183a": 1.06430668,
                     "H182a": 1.08189835,
                     "H181a": 1.09987985,
                     "H180a": 1.11826206,
                     "H179a": 1.13705618,
                     "H178a": 1.15627383,
                     "H177a": 1.17592701,
                     "H176a": 1.19602811,
                     "H175a": 1.21658997,
                     "H174a": 1.23762588,
                     "H173a": 1.25914957,
                     "H172a": 1.28117526,
                     "H171a": 1.30371768,
                     "H170a": 1.32679206,
                     "H169a": 1.35041420,
                     "H168a": 1.37460043,
                     "H167a": 1.39936771,
                     "H166a": 1.42473359,
                     "H165a": 1.45071626,
                     "H164a": 1.47733457,
                     "H163a": 1.50460810,
                     "H162a": 1.53255712,
                     "H161a": 1.56120269,
                     "H160a": 1.59056662,
                     "H159a": 1.62067158,
                     "H158a": 1.65154111,
                     "H157a": 1.68319962,
                     "H156a": 1.71567248,
                     "H155a": 1.74898605,
                     "H154a": 1.78316770,
                     "H153a": 1.81824591,
                     "H152a": 1.85425027,
                     "H151a": 1.89121153,
                     "H150a": 1.92916170,
                     "H149a": 1.96813408,
                     }


def create_spw_dict(myvis, min_continuum_chanwidth_kHz=50):
    '''
    Create the SPW dict from MS metadata. Split based on continuum and
    use the line dictionary to match line identifications.
    '''

    # TODO: need to CASA 6 proof.
    from taskinit import ms

    ms.open(myvis)

    metadata = ms.metadata()

    spw_dict = {}

    # Our SPW setup is the same for all fields.
    spw_ids = metadata.spwsforfield(0)

    # Identify which target we're looking at.
    # TODO: handling of multiple targets? Would require separate
    # setups (though SPW ids probably the same, so that's likely fine)
    first_targ_scan = metadata.scansforintent("*TARGET*")[0]
    targ_fieldname = metadata.fieldnames()[metadata.fieldsforscan(first_targ_scan)[0]]

    gal_vsys = None
    for gal in target_vsys_kms:

        if gal in targ_fieldname:
            gal_vsys = target_vsys_kms[gal]
            break

    if gal_vsys is None:
        raise ValueError("Cannot identify which target galaxy is observed"
                         " from field name {}".format(targ_fieldname))

    # Below is a sketch of doing this for all target fields if there are
    # multiple target galaxies.
    # np.array(metadata.fieldnames())[metadata.fieldsforintent("*TARGET*")]

    # Convert rest to observed based on the target
    lineobs_dict_GHz = {}

    for line in linerest_dict_GHz:

        lineobs_dict_GHz[line] = lines_rest2obs(linerest_dict_GHz[line], gal_vsys)

    # Counters for continuum windows in basebands A0C0, B0D0.
    cont_A_count = 0
    cont_B_count = 0

    # Populate the SPW info.
    for spwid in spw_ids:

        # Original name
        spw_name = metadata.namesforspws(spwid)[0]

        # Channel width
        chan_width = metadata.chanwidths(spwid)[0]

        # Bandwidth
        band_width = metadata.bandwidths(spwid)

        # N chans
        nchan = metadata.nchan(spwid)

        # Centre freq.
        # ctr_freq = metadata.chanfreqs
        freqs_lsrk = ms.cvelfreqs(spwids=[spwid], outframe='LSRK')

        # Convert from Hz to kHz
        ctr_freq = freqs_lsrk[nchan // 2 - 1] / 1e3

        # Baseband
        bband = spw_name.split("#")[1]

        # Ncorr
        # ncorr = metadata.ncorrforpol(spwid)

        # Check if continuum or not. If so, assign a unique tag with
        # baseband and number.
        if chan_width >= min_continuum_chanwidth_kHz * 1e3:

            if bband.startswith("A"):
                spw_label = "continuum_A{}".format(cont_A_count)
                cont_A_count += 1
            else:
                spw_label = "continuum_B{}".format(cont_B_count)
                cont_B_count += 1

        # Otherwise do a line match
        else:

            line_match = []

            for line in lineobs_dict_GHz:

                obs_freq = lineobs_dict_GHz[line] * 1e9

                if obs_freq > freqs_lsrk.min() and obs_freq < freqs_lsrk.max():

                    line_match.append(line)

            if len(line_match) == 0:
                raise ValueError("Unable to match spectral line.")

            spw_label = "-".join(line_match)

        spw_dict[spwid] = {'label': spw_label,
                           'origname': spw_name,
                           'chanwidth': chan_width,
                           'bandwidth': band_width,
                           # 'ncorr': ncorr,
                           'centerfreq': ctr_freq,
                           'baseband': bband}

    ms.close()

    return spw_dict


spw_dict_20A346 = {}

# Map each baseband separately
# A0CO mostly lines
# Format:
# Name: [num, "fullname", nchan, chanwidth, totbw, ctrfreq, "corrs"]
spw_dict_20A346["A0C0"] = \
    {"contA0": {"num": 0, "origname": "EVLA_L#A0C0#0", "nchan": 64, "freq0": 1000.170,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1031.6704,
                "corrs": "RR  RL  LR  LL"},
     "H175a": {"num": 1, "origname": "EVLA_L#A0C0#1", "nchan": 128, "freq0": 1215.869,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1217.8538,
               "corrs": "RR  LL"},
     "H171a": {"num": 2, "origname": "EVLA_L#A0C0#2", "nchan": 128, "freq0": 1303.077,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1305.0610,
               "corrs": "RR  LL"},
     "H170a": {"num": 3, "origname": "EVLA_L#A0C0#3", "nchan": 128, "freq0": 1326.172,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1328.1564,
               "corrs": "RR  LL"},
     "contA1_HIbackup": {"num": 4, "origname": "EVLA_L#A0C0#4", "nchan": 64, "freq0": 1384.170,
                         "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1415.6704,
                         "corrs": "RR  RL  LR  LL"},
     "HI": {"num": 5, "origname": "EVLA_L#A0C0#5", "nchan": 4096, "freq0": 1417.883,
            "chanwidth": 1.953, "bandwidth": 8000.0, "centerfreq": 1421.8816,
            "corrs": "RR  LL"},
     "H166a": {"num": 6, "origname": "EVLA_L#A0C0#6", "nchan": 128, "freq0": 1424.203,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1426.1872,
               "corrs": "RR  LL"},
     "OH1612": {"num": 7, "origname": "EVLA_L#A0C0#7", "nchan": 512, "freq0": 1611.884,
                "chanwidth": 7.812, "bandwidth": 4000.0, "centerfreq": 1613.8804,
                "corrs": "RR  LL"},
     "contA2_OHbackup1": {"num": 8, "origname": "EVLA_L#A0C0#8", "nchan": 64, "freq0": 1640.170,
                          "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1671.6704,
                          "corrs": "RR  RL  LR  LL"},
     "H158a": {"num": 9, "origname": "EVLA_L#A0C0#9", "nchan": 128, "freq0": 1651.217,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1653.2015,
               "corrs": "RR  LL"},
     # THIS CHANGES WITH TARGETS! Will need to adjust!
     "OH1665_1667": {"num": 10, "origname": "EVLA_L#A0C0#10", "nchan": 1024, "freq0": 1664.083,
                     "chanwidth": 7.812, "bandwidth": 8000.0, "centerfreq": 1668.0796,
                     "corrs": "RR  LL"},
     "contA3_OHbackup2": {"num": 11, "origname": "EVLA_L#A0C0#11", "nchan": 64, "freq0": 1704.170,
                          "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1735.6704,
                          "corrs": "RR  RL  LR  LL"},
     "H156a": {"num": 12, "origname": "EVLA_L#A0C0#12", "nchan": 128, "freq0": 1715.407,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1717.3913,
               "corrs": "RR  LL"},
     "OH1720": {"num": 13, "origname": "EVLA_L#A0C0#13", "nchan": 512, "freq0": 1720.170,
                "chanwidth": 7.812, "bandwidth": 4000.0, "centerfreq": 1722.1665,
                "corrs": "RR  LL"},
     "H154a": {"num": 14, "origname": "EVLA_L#A0C0#14", "nchan": 128, "freq0": 1782.964,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1784.9481,
               "corrs": "RR  LL"},
     "H153a": {"num": 15, "origname": "EVLA_L#A0C0#15", "nchan": 128, "freq0": 1818.074,
               "chanwidth": 31.250, "bandwidth": 4000.0, "centerfreq": 1820.0583,
               "corrs": "RR  LL"},
     }

# B0D0 dedicated continuum
spw_dict_20A346["B0D0"] = \
    {"contB0": {"num": 16, "origname": "EVLA_L#B0D0#16", "nchan": 64, "freq0": 988.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1019.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB1": {"num": 17, "origname": "EVLA_L#B0D0#17", "nchan": 64, "freq0": 1052.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1083.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB2": {"num": 18, "origname": "EVLA_L#B0D0#18", "nchan": 64, "freq0": 1116.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1147.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB3": {"num": 19, "origname": "EVLA_L#B0D0#19", "nchan": 64, "freq0": 1180.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1211.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB4": {"num": 20, "origname": "EVLA_L#B0D0#20", "nchan": 64, "freq0": 1244.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1275.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB5": {"num": 21, "origname": "EVLA_L#B0D0#21", "nchan": 64, "freq0": 1308.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1339.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB6": {"num": 22, "origname": "EVLA_L#B0D0#22", "nchan": 64, "freq0": 1372.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1403.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB7": {"num": 23, "origname": "EVLA_L#B0D0#23", "nchan": 64, "freq0": 1436.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1467.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB8": {"num": 24, "origname": "EVLA_L#B0D0#24", "nchan": 64, "freq0": 1500.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1531.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB9": {"num": 25, "origname": "EVLA_L#B0D0#25", "nchan": 64, "freq0": 1564.000,
                "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1595.5000,
                "corrs": "RR  RL  LR  LL"},
     "contB10": {"num": 26, "origname": "EVLA_L#B0D0#26", "nchan": 64, "freq0": 1628.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1659.5000,
                 "corrs": "RR  RL  LR  LL"},
     "contB11": {"num": 27, "origname": "EVLA_L#B0D0#27", "nchan": 64, "freq0": 1692.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1723.5000,
                 "corrs": "RR  RL  LR  LL"},
     "contB12": {"num": 28, "origname": "EVLA_L#B0D0#28", "nchan": 64, "freq0": 1756.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1787.5000,
                 "corrs": "RR  RL  LR  LL"},
     "contB13": {"num": 29, "origname": "EVLA_L#B0D0#29", "nchan": 64, "freq0": 1820.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1851.5000,
                 "corrs": "RR  RL  LR  LL"},
     "contB14": {"num": 30, "origname": "EVLA_L#B0D0#30", "nchan": 64, "freq0": 1884.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1915.5000,
                 "corrs": "RR  RL  LR  LL"},
     "contB15": {"num": 31, "origname": "EVLA_L#B0D0#31", "nchan": 64, "freq0": 1948.000,
                 "chanwidth": 1000.000, "bandwidth": 64000.0, "centerfreq": 1979.5000,
                 "corrs": "RR  RL  LR  LL"},
     }
