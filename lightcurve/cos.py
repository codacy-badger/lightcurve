"""
Holder of Cosmic Origins Spectrograph (COS) classes and utilities

"""

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

from astropy.io import fits
import os
import numpy as np
from scipy.interpolate import interp1d

from .utils import expand_refname

#__all__ = ['extract_index', 'get_both_filenames']

#-------------------------------------------------------------------------------

def extract(filename, **kwargs):
    """ Loop over HDUs and extract the lightcurve

    This is the main driver of the lightcuve extracion, and definitely
    needs some better documentation.

    """

    """
                if alt:
                    seg = input_hdus.keys()[0]
                    print('Filtering out times of SUN_ALT > {}'.format(alt))
                    print('--Total time in exposure: {}'.format(
                            input_hdus[seg][1].header['EXPTIME']))
                    try:
                        timeline = input_hdus[seg]['TIMELINE'].data
                        day_index = np.where(timeline['SUN_ALT'] > alt)

                        if len(day_index[0]):
                            bad_min = timeline['TIME'][day_index].min()
                            bad_max = timeline['TIME'][day_index].max()

                            print('--Removing times from {} to {} seconds'.format(bad_min, bad_max))
                            lc_index = np.where((times < bad_min) |
                                                (times > bad_max))

                            filter(lc_index)

                        else:
                            print('--No times matching criteria, no filtering performed')

                    except KeyError:
                        print('Warning: No TIMELINE extension found, make sure this dataset')
                        print('         was calibrated with the *_spt.fits file present')

    """

    step = kwargs.get('step', 1)
    wlim = kwargs.get('wlim', (2, 10000))
    xlim = kwargs.get('xlim', (0, 16384))
    ylim = kwargs.get('ylim', None)
    filter_airglow = kwargs.get('filter_airglow', True)

    SECOND_PER_MJD = 1.15741e-5

    input_files, input_hdus = collect_inputs(filename)
    print('Extracting from: {}'.format(input_files))
    print("Using wlim: {}".format(wlim))
    print("      step: {}".format(step))

    #time = np.array([round(val, 3) for val in hdu[1].data['time']]).astype(np.float64)

    end = 0
    for segment, hdu in input_hdus.iteritems():
        data_max = hdu[1].data['TIME'].max()
        if data_max > end:
            end = data_max


    all_steps = np.arange(0, end+step, step)

    if all_steps[-1] > end:
        truncate = True
    else:
        truncate = False

    gross = 0
    flux = 0
    background = 0
    background_flux = 0

    for segment, hdu in input_hdus.iteritems():

        ### Source Calculation
        print('Segment {} fluxcal'.format(segment))
        if not ylim:
            ystart, yend = get_extraction_region(hdu, segment, 'spectrum')
        else:
            ystart, yend = ylim[0], ylim[1]

        print(xlim, ystart, yend, wlim, hdu[1].header['sdqflags'])
        index = extract_index(hdu,
                              xlim[0], xlim[1],
                              ystart, yend,
                              wlim[0], wlim[1],
                              hdu[1].header['sdqflags'],
                              filter_airglow=filter_airglow)
        print("{} #{} events".format(segment, len(index)))

        try:
            max_xpix = round(min(hdu['events'].data['XCORR'][index].max(), xlim[1]))
            min_xpix = round(max(hdu['events'].data['XCORR'][index].min(), xlim[0]))
            n_pixels = (max_xpix - min_xpix) + 1
        except ValueError:
            n_pixels = 1

        gross += np.histogram(hdu['events'].data['time'][index],
                              all_steps,
                              weights=hdu['events'].data['epsilon'][index])[0]

        response_array = get_fluxes(hdu, index).mean()
        tds_corr = get_tds(hdu, index)

        weights = hdu['events'].data['epsilon'][index] / step / tds_corr / response_array
        flux +=  np.histogram(hdu['events'].data['time'][index], all_steps, weights=weights)[0] / n_pixels


        ### Background calculation
        #print('Background fluxcal')
        bstart, bend = get_extraction_region( hdu, segment, 'background1' )
        index = extract_index(hdu,
                              xlim[0], xlim[1],
                              bstart, bend,
                              wlim[0], wlim[1],
                              hdu[1].header['sdqflags'],
                              filter_airglow=filter_airglow)

        bstart, bend = get_extraction_region( hdu, segment, 'background2' )
        index = np.hstack( (index, extract_index(hdu,
                                                 xlim[0], xlim[1],
                                                 bstart, bend,
                                                 wlim[0], wlim[1],
                                                 hdu[1].header['sdqflags'],
                                                 filter_airglow=filter_airglow) ) )

        b_corr = ( (bend - bstart) / (yend - ystart) ) / 2.
        background += b_corr * np.histogram(hdu['events'].data['time'][index],
                                            all_steps,
                                            weights=hdu['events'].data['epsilon'][index] )[0]

        response_array = get_fluxes(hdu, index)
        tds_corr = get_tds(hdu, index)
        weights = hdu['events'].data['epsilon'][index] / step / tds_corr / response_array
        background_flux +=  (b_corr * np.histogram(hdu['events'].data['time'][index],
                                                   all_steps,
                                                   weights=weights)[0]) / n_pixels


    gross = gross
    flux = flux - background_flux
    background = background
    mjd = hdu[1].header['EXPSTART'] + np.array(all_steps[:-1]) * SECOND_PER_MJD
    bins = np.ones(len(gross)) * step
    times = all_steps[:-1]

    if truncate:
        gross = gross[:-1]
        flux = flux[:-1]
        background = background[:-1]
        mjd = mjd[:-1]
        bins = bins[:-1]
        times = times[:-1]


    data = [times, mjd, bins, gross, background, flux]
    columns = ('times', 'mjd' ,'bins', 'gross', 'background', 'flux')
    meta = {}

    return data, columns, meta

#-------------------------------------------------------------------------------

def collect_inputs(filename):
    """Populate HDU dictionary from available corrtag files

    """

    with fits.open(filename) as hdu:
        if hdu[0].header['detector'] == 'NUV':
            all_filenames = [filename]

            if hdu[0].header['opt_elem'] == 'G230L':
                all_hdu = {'A':hdu, 'B':hdu}
            else:
                all_hdu = {'A':hdu, 'B':hdu, 'C':hdu}

        elif hdu[0].header['detector'] == 'FUV':
            file_a, file_b = get_both_filenames(filename)

            all_hdu = dict()
            all_filenames = []
            for name, letter in zip([file_a, file_b], ['A', 'B']):
                if os.path.exists(name):
                    all_filenames.append(name)
                    all_hdu[letter] = fits.open(name, ignore_missing_end=True)

    return all_filenames, all_hdu

#-------------------------------------------------------------------------------

def extract_index(hdu, x_start, x_end,
                  y_start, y_end, w_start, w_end, sdqflags=0,
                  filter_airglow=True):
    """
    Extract event indeces from given HDU using input parameters.

    Wavelength regions containing geocoronal airglow emission will be excluded
    automatically.  These regions include Lyman Alpha between 1214 and 1217
    Angstroms and Oxygen I from 1300 to 1308.


    Parameters
    ----------
    hdu : HDUlist
        Header Data Unit from COS corrtag file
    x_start : float
        Lower bound of events in pixel space
    x_end : float
        Upper bound of events in pixel space
    y_start : float
        Lower bound of events in pixel space
    y_end : float
        Upper bound of events in pixel space
    w_start : float
        Lower bound of events in wavelength space
    w_end : float
        Upper bound of events in wavelength space
    sdqflags : int
        Bitwise DQ value of bad events

    Returns
    -------
    data_index : np.ndarray
        Indeces of desired events

    """

    if filter_airglow:
        lyman = (1214, 1217)
        oxygen = (1300, 1308)
    else:
        lyman = (w_end, w_start)
        oxygen = (w_end, w_start)

    data_index = np.where( ( hdu[1].data['XCORR'] >= x_start ) &
                           ( hdu[1].data['XCORR'] < x_end ) &

                           ( hdu[1].data['YCORR'] >= y_start ) &
                           ( hdu[1].data['YCORR'] < y_end ) &

                           np.logical_not( hdu[1].data['DQ'] & sdqflags ) &

                           ( (hdu[1].data['WAVELENGTH'] > w_start) &
                             (hdu[1].data['WAVELENGTH'] < w_end) ) &

                           ( (hdu[1].data['WAVELENGTH'] > lyman[1]) |
                             (hdu[1].data['WAVELENGTH'] < lyman[0]) ) &
                           ( (hdu[1].data['WAVELENGTH'] > oxygen[1]) |
                             (hdu[1].data['WAVELENGTH'] < oxygen[0]) )
                           ) [0]

    return data_index

#-------------------------------------------------------------------------------

def get_both_filenames(filename):
    """ Get a list of both filenames for FUV data

    Regardless if rootname_corrtag_a.fits or rootname_corrtag_b.fits
    is passed in, both will be returned in a list.

    Parameters
    ----------
    filename : str
        full path to COS file

    Returns
    -------
    files : tuple
        rootname_corrtag_a.fits, rotname_corrtag_b.fits

    """

    if '_a.fits' in filename:
        other_filename = filename.replace('_a.fits', '_b.fits')
    elif '_b.fits' in filename:
        other_filename = filename.replace('_b.fits', '_a.fits')
    else:
        raise ValueError("filename doesn't match FUV convention".format(filename))

    filename_list = [filename, other_filename]
    filename_list.sort()

    return (filename_list[0], filename_list[1])

#-------------------------------------------------------------------------------

def get_extraction_region(hdu, segment, mode='spectrum'):
    """Get y_start,y_end for given extraction

    """

    if mode == 'spectrum':
        height =  hdu[1].header['SP_HGT_%s' % (segment)]
        location = hdu[1].header['SP_LOC_%s' % (segment)]

    elif mode == 'background1':
        height =  hdu[1].header['B_HGT1_%s' % (segment)]
        location = hdu[1].header['B_BKG1_%s' % (segment)]

    elif mode == 'background2':
        height =  hdu[1].header['B_HGT2_%s' % (segment)]
        location = hdu[1].header['B_BKG2_%s' % (segment)]

    y_start = location - height//2
    y_end = location + height//2

    return y_start, y_end

#-------------------------------------------------------------------------------

def get_fluxes(hdu, index):
    """ Return response curve and wavelength range for specified mode
    """

    fluxtab = hdu[0].header.get('FLUXTAB', '')

    fluxfile = expand_refname(fluxtab)

    if not len(index):
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]

    if (not fluxfile) or (not os.path.exists( fluxfile ) ):
        print(' WARNING: Fluxfile not available %s,' % fluxfile )
        print(' using unity flux calibration instead.' )
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]


    flux_hdu = pyfits.open(fluxfile)
    setting_index = np.where( (flux_hdu[1].data['SEGMENT'] == hdu[0].header['segment']) &
                           (flux_hdu[1].data['OPT_ELEM'] == hdu[0].header['opt_elem']) &
                           (flux_hdu[1].data['CENWAVE'] == hdu[0].header['cenwave']) &
                           (flux_hdu[1].data['APERTURE'] == hdu[0].header['aperture']) )[0]
    if len( setting_index ) == 0:
        print('No row in fluxtab found for this dataset, no FLUXCAL performed')
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]
    else:
        raise ValueError('Too many rows found: {}'.format( len(setting_index) ) )


    resp_wave = flux_hdu[1].data[setting_index]['WAVELENGTH'].flatten()
    response = flux_hdu[1].data[setting_index]['SENSITIVITY'].flatten()

    data_max = hdu['events'].data['wavelength'][index].max()
    data_min = hdu['events'].data['wavelength'][index].min()

    if data_max > resp_wave.max():
        print( "Expanding minumum response curve by {}".format( data_max - resp_wave.max() ) )
        resp_wave[ np.argmax( resp_wave ) ] = data_max

    if data_min < resp_wave.min():
        print( "Expanding minimum response curve by {}".format( data_min - resp_wave.min() ) )
        resp_wave[ np.argmin( resp_wave ) ] = data_min

    interp_func = interp1d( resp_wave, response )
    all_resp = interp_func( hdu[ 'events' ].data['wavelength'][index] )

    return all_resp

#-------------------------------------------------------------------------------

def get_tds(hdu, index):
    """ return tds correction for each event
    """

    try:
        tdstab = hdu[0].header['TDSTAB']
    except KeyError:
        tdstab = ''


    tdsfile = expand_refname( tdstab )

    if not len(index):
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]

    if (not tdsfile) or (not os.path.exists( tdsfile ) ):
        print(' WARNING: tdsfile not available %s,' % tdsfile )
        print(' using unity TDS correction instead.' )
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]

    tds_data = fits.getdata( tdsfile, ext=1 )
    REF_TIME = fits.getval( tdsfile, 'REF_TIME', ext=1)
    mode_index = np.where( (tds_data['OPT_ELEM'] == hdu[0].header['opt_elem'] ) &
                           (tds_data['APERTURE'] == hdu[0].header['aperture'] ) &
                           (tds_data['SEGMENT'] == hdu[0].header['segment'] ) )[0]


    if len( mode_index ) == 0:
        print('No row in tdstab found for this dataset, no TDSCORR performed')
        return np.ones( hdu[ 'events' ].data['time'].shape )[index]
    elif len( mode_index ) > 1:
        raise ValueError('Too many rows found: {}'.format( len(mode_index) ) )

    mode_line = tds_data[ mode_index ]

    tds_nt = mode_line['NT'][0]
    tds_wavelength = mode_line['WAVELENGTH'][0]
    smaller_index = np.where( mode_line['TIME'][0][:tds_nt] < hdu[1].header['EXPSTART'] )[0]
    time_index = smaller_index.max()

    tds_slope = mode_line['SLOPE'][0]
    tds_intercept = mode_line['INTERCEPT'][0]

    calculate_drop = lambda time, ref_time, slope, intercept: \
        ( (( time - ref_time ) * slope) / (365.25*100) ) + intercept

    correction_array = np.zeros( len(tds_wavelength) )
    for i, wave in enumerate( tds_wavelength ):
        correction = calculate_drop( hdu[1].header['EXPSTART'],
                                     REF_TIME,
                                     tds_slope[time_index,i],
                                     tds_intercept[time_index,i] )
        correction_array[i] = correction

    #-------
    # interpolate onto input arrays
    #------

    interp_function = interp1d( tds_wavelength, correction_array, 1 )
    response_correction = interp_function( hdu[1].data['wavelength'][index] )

    return response_correction

#-------------------------------------------------------------------------------
