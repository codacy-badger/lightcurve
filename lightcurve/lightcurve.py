"""
Contains the basic LightCurve object which is inherited by the subclasses.

"""

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

__all__ = ['LightCurve', 'composite']

import astropy
import scipy
import numpy as np
import os
from datetime import datetime
from astropy.io import fits
from astropy.table import Table, vstack

from .version import version as __version__
from .io import check_filetype, open_lightcurve
from .cos import extract as extract_cos
from .cos import get_both_filenames
from .stis import extract as extract_stis

#-------------------------------------------------------------------------------

class LightCurve(Table):
    """
    Returns
    -------
    lightcurve object

    """

    def __init__(self, filename=None, **kwargs):
        """ Instantiate an empty LightCurve object.

        LightCurves must contain:
            gross
            bins (timestep)
            times
            mjd
            background
            flux

        All values are currently set to empty arrays.

        """

        if isinstance(filename, Table):
            columns = list(filename.columns)
            data = [filename[item].data for item in columns]
            meta = filename.meta
            meta['outname'] = None

        elif filename == None:
           print("Initializing emtpy LightCurve")

           data = [[], [], [], [], [], []]
           columns = ('times',
                      'mjd',
                      'bins',
                      'gross',
                      'background',
                      'flux')
           meta = {'filename': None}

        else:
            filetype = check_filetype(filename)
            if filetype == 'cos_corrtag':
                data, columns, meta = extract_cos(filename, **kwargs)
            elif filetype == 'stis_tag' or filetype == 'stis_corrtag':
                data, columns, meta = extract_stis(filename, **kwargs)
            elif filetype == 'lightcurve':
                data, columns, meta = open_lightcurve(filename)
            else:
                raise IOError("Filetype not recognized: {}".format(filetype))

            meta['outname'] = filename[:9] + '_curve.fits'
            meta['filetype'] = filetype

        super(LightCurve, self).__init__(data,
                                         names=columns,
                                         meta=meta)


    def __add__(self, other):
        """ Overload the '+' operator.
        """
        raise NotImplementedError("I'm not yet sure how to do this")


    def __sub__(self, other):
        """ Overload the - operator """
        raise NotImplementedError("I'm not yet sure how to do this")


    def __mul__(self, other):
        """ Overload the * operator """
        raise NotImplementedError("I'm not yet sure how to do this")


    def __div__(self, other):
        """ Overload the / operator """
        raise NotImplementedError("I'm not yet sure how to do this")


    def __str__(self):
        """Prettier representation of object instanct"""

        return "Lightcurve Object"


    def concatenate(self, other, handle_conflicts='warn'):
        """Concatenate two lightcurve tables.
        """

        new_table = vstack([self._to_table(), other._to_table()], metadata_conflicts=handle_conflicts)
        return LightCurve(new_table)


    def _to_table(self):
        """Strip out all the LightCurve stuff and return Table instance
        """

        columns = list(self.columns)
        data = [self[item].data for item in columns]
        meta = self.meta

        return Table(data, names=columns, meta=meta)

    @property
    def counts(self):
        """ Calculate counts array

        Counts are calculated as the gross - background


        Returns
        -------
        counts : np.ndarray
            Array containing the calculated counts

        """

        if not len(self['gross']):
            return self['gross'].copy()
        else:
            return self['gross'] - self['background']


    @property
    def error(self):
        """ Calculate error array

        Error is calculated as sqrt( gross + background )

        Returns
        -------
        error : np.ndarray
            Array containing the calculated error

        """

        if not len(self['gross']):
            return self['gross'].copy()
        else:
            return np.sqrt(self['gross'] + self['background'])


    @property
    def flux_error(self):
        """ Estimate the error in the flux array

        Flux error is currently estimated as having the same magnitude
        relative to flux as the error has to counts.  Very simple approximation
        for now

        Returns
        -------
        flux_error : np.ndarray
            Array containing the calculated error in flux

        """

        if not len(self['gross']):
            return self['gross'].copy()
        else:
            return (self.error / self.counts) *  self['flux']


    @property
    def net(self):
        """ Calculate net array

        Net is calculated as counts / time

        Returns
        -------
        net : np.ndarray
            Array containing calculated net

        """

        if not len(self.counts):
            return self.counts.copy()
        else:
            return self.counts / self['bins'].astype(np.float64)


    @property
    def signal_to_noise(self):
        """ Quick signal to noise estimate

        S/N is calculated as the ratio of gross to error

        Returns
        -------
        sn_ratio : np.ndarray
            Array containing calculated signal to noise ratio

        """

        if not len(self['gross']):
            return self['gross'].copy()
        else:
            return self['gross'] / self.error


    def filter(self, indices):
        """ Keep only a section of the whole lightcurve

        Modifies the LC in place

        Parameters
        ----------
        indices : np.ndarray
            Array of indexes to keep

        """

        self = self[indices]


    def write(self, outname=None, clobber=False):
        """ Write lightcurve out to FITS file

        Parameters
        ----------
        outname : bool or str
            Either True/False, or output name

        clobber : bool
            Allow overwriting of existing file with same name

        """

        if isinstance(outname, str):
            self.meta['outname'] = outname

        hdu_out = fits.HDUList(fits.PrimaryHDU())

        #-- Primary header
        hdu_out[0].header['GEN_DATE'] = (str(datetime.now()), 'Creation Date')
        hdu_out[0].header['LC_VER'] = (__version__, 'lightcurve version used')
        hdu_out[0].header['AP_VER'] = (astropy.__version__, 'Astropy version used')
        hdu_out[0].header['NP_VER'] = (np.__version__, 'Numpy version used')
        hdu_out[0].header['SP_VER'] = (scipy.__version__, 'Scipy version used')
        hdu_out[0].header.add_blank('', before='GEN_DATE')
        hdu_out[0].header.add_blank('{0:{fill}{align}67}'.format(' Lightcurve extraction keywords ',
                                                                 fill='-',
                                                                 align='^'), before='GEN_DATE')
        hdu_out[0].header.add_blank('', before='GEN_DATE')
        #hdu_out[0].header['WMIN'] = kwargs



        hdu_out[0].header.add_blank('', after='SP_VER')
        hdu_out[0].header.add_blank('{0:{fill}{align}67}'.format(' Source Data keywords ',
                                                                 fill='-',
                                                                 align='^'), after='SP_VER')
        hdu_out[0].header.add_blank('', after='SP_VER')

        for in_hdu in self.meta['hdus'].itervalues():
            try:
                hdu_out[0].header.extend(in_hdu[0].header, end=True)
            except AttributeError:
                pass


        #-- Ext 1 table data
        bins_col = fits.Column('bins',
                               'D',
                               'second',
                               array=self['bins'])

        times_col = fits.Column('times',
                                'D',
                                'second',
                                array=self['times'])

        mjd_col = fits.Column('mjd',
                              'D',
                              'MJD',
                              array=self['mjd'])

        gross_col = fits.Column('gross',
                                'D',
                                'counts',
                                array=self['gross'])

        counts_col = fits.Column('counts',
                                 'D',
                                 'counts',
                                 array=self.counts)

        net_col = fits.Column('net',
                              'D',
                              'counts/s',
                               array=self.net)

        flux_col = fits.Column('flux',
                               'D',
                               'ergs/s',
                               array=self['flux'])

        flux_error_col = fits.Column('flux_error',
                                     'D',
                                     'ergs/s',
                                      array=self.flux_error)

        bkgnd_col = fits.Column('background',
                                'D',
                                'cnts',
                                 array=self['background'])

        error_col = fits.Column('error',
                                'D',
                                'counts',
                                array=self.error)

        tab = fits.new_table([bins_col,
                              times_col,
                              mjd_col,
                              gross_col,
                              counts_col,
                              net_col,
                              flux_col,
                              flux_error_col,
                              bkgnd_col,
                              error_col])
        hdu_out.append(tab)



        #-- Ext 1 header
        hdu_out[1].header.add_blank('')
        hdu_out[1].header.add_blank('{0:{fill}{align}67}'.format(' Lightcurve extraction keywords ',
                                                                 fill='-',
                                                                 align='^'))
        hdu_out[1].header.add_blank('')


        hdu_out[1].header.add_blank('')
        hdu_out[1].header.add_blank('{0:{fill}{align}67}'.format(' Source Data keywords ',
                                                                 fill='-',
                                                                 align='^'))
        hdu_out[1].header.add_blank('')

        for in_hdu in self.meta['hdus'].itervalues():
            try:
                hdu_out[1].header.extend(in_hdu[1].header, end=True)
            except AttributeError:
                pass

        if self.meta['outname'].endswith('.gz'):
            print("Nope, can't write to gzipped files")
            self.meta['outname'] = self.meta['outname'][:-3]

        hdu_out.writeto(self.meta['outname'], clobber=clobber)

#-------------------------------------------------------------------------------

def composite(filelist, output, trim=True, **kwargs):
    """Creates a composite lightcurve from files in filelist and saves
    it to the save_loc.

    Parameters
    ----------
    filelist : list
        A list of full paths to the input files.
    output : string
        The path to the location in which the composite lightcurve is saved.
    trim : bool, opt
        Trim wavelengths to common ranges for all files
    """

    print("Creating composite lightcurve from:")
    print("\n".join(filelist))

    wmin = 912
    wmax = 3000

    for filename in filelist:
        with fits.open(filename) as hdu:
            dq = hdu[1].data['DQ']
            wave = hdu[1].data['wavelength']
            xcorr = hdu[1].data['xcorr']
            ycorr = hdu[1].data['ycorr']
            sdqflags = hdu[1].header['SDQFLAGS']

            if (hdu[0].header['INSTRUME'] == "COS") and (hdu[0].header['DETECTOR'] == 'FUV'):
                other_file = [item for item in get_both_filenames(filename) if not item == filename][0]
                if os.path.exists(other_file):
                    with fits.open(other_file) as hdu_2:
                        dq = np.hstack([dq, hdu_2[1].data['DQ']])
                        wave = np.hstack([wave, hdu_2[1].data['wavelength']])
                        xcorr = np.hstack([xcorr, hdu_2[1].data['xcorr']])
                        ycorr = np.hstack([ycorr, hdu_2[1].data['ycorr']])
                        sdqflags |= hdu_2[1].header['SDQFLAGS']

            index = np.where((np.logical_not(dq & sdqflags)) &
                             (wave > 500) &
                             (xcorr >= 0) &
                             (ycorr >= 0))

            if not len(index[0]):
                print('No Valid events')
                continue

            wmax = min(wmax, wave[index].max())
            wmin = max(wmin, wave[index].min())
            print(wmin, '-->', wmax)


    if trim:
        print('Using wavelength range of: {}-{}'.format(wmin, wmax))
        kwargs['wlim'] = (wmin, wmax)

    for i, filename in enumerate(filelist):
        print(filename)

        if i == 0:
            out_lc = LightCurve(filename, **kwargs)
        else:
            new_lc = LightCurve(filename, **kwargs)
            out_lc = out_lc.concatenate(new_lc)

    out_lc.write(output, clobber=True)

#-------------------------------------------------------------------------------
