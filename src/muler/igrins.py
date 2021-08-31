r"""
IGRINS Spectrum
---------------

A container for an IGRINS spectrum of :math:`M=28` total total orders :math:`m`, each with vectors for wavelength flux and uncertainty, e.g. :math:`F_m(\lambda)`.


IGRINSSpectrum
##############
"""

import warnings
from muler.echelle import EchelleSpectrum, EchelleSpectrumList
from astropy.time import Time
import numpy as np
import astropy
from astropy.io import fits
from astropy import units as u
from astropy.wcs import WCS, FITSFixedWarning
from astropy.nddata import StdDevUncertainty

import copy


#  See Issue: https://github.com/astropy/specutils/issues/779
warnings.filterwarnings(
    "ignore", category=astropy.utils.exceptions.AstropyDeprecationWarning
)
warnings.filterwarnings("ignore", category=FITSFixedWarning)
# See Issue: https://github.com/astropy/specutils/issues/800
warnings.filterwarnings("ignore", category=RuntimeWarning)


# Convert PLP index number to echelle order m
## Note that these technically depend on grating temperature
## For typical operating temperature, offsets should be exact.
grating_order_offsets = {"H": 98, "K": 71}


class IGRINSSpectrum(EchelleSpectrum):
    r"""
    A container for IGRINS spectra

    Args:
        file (str): A path to a reduced IGRINS spectrum from plp of file type .spec.fits
            or .spec_a0v.fits.
        wavefile (str):  A path to a reduced IGRINS spectrum storing the wavelength solution
            of file type .wave.fits.
        order (int): which spectral order to read
        cached_hdus (list) :
            List of two or three fits HDUs, one for the spec.fits/spec_a0v.fits, one for the
            sn.fits file, and one optional one for the .wave.fits file
            to reduce file I/O for multiorder access.
            If provided, must give both (or three) HDUs.  Optional, default is None.
    """

    def __init__(self, *args, file=None, wavefile=None, order=10, cached_hdus=None, **kwargs):

        self.ancillary_spectra = None
        self.noisy_edges = (450, 1950)
        self.instrumental_resolution = 45_000.0

        if file is not None:
            # Determine the band
            if "SDCH" in file:
                band = "H"
            elif "SDCK" in file:
                band = "K"
            else:
                raise NameError("Cannot identify file as an IGRINS spectrum")
            grating_order = grating_order_offsets[band] + order

            sn_file = file[19] + "sn.fits"
            if cached_hdus is not None:
                hdus = cached_hdus[0]
                sn_hdus = cached_hdus[1]
                if wavefile is not None:
                    wave_hdus = cached_hdus[2]
            else:
                hdus = fits.open(str(file))
                try:
                    sn_hdus = fits.open(sn_file)
                except:
                    sn_hdus = None
                if wavefile is not None:
                    wave_hdus = fits.open(wavefile)
            hdr = hdus[0].header
            if ".spec_a0v.fits" in file:
                lamb = hdus["WAVELENGTH"].data[order].astype(np.float64) * u.micron
                flux = hdus["SPEC_DIVIDE_A0V"].data[order].astype(np.float64) * u.ct
            elif "spec.fits" in file and wavefile is not None:
                lamb = wave_hdus[0].data[order].astype(np.float64) * 1e-3 * u.micron #Note .wave.fits and .wavesol_v1.fts files store their wavelenghts in nm so they need to be converted to microns
                flux = hdus[0].data[order].astype(np.float64) * u.ct
            else:
                raise Exception("File "+file+" is the wrong file type.  It should be .spec_a0v.fits or .spec.fits.  If it is .spec.fits, you might not have specified wavefile correctly.")
            meta_dict = {
                "x_values": np.arange(0, 2048, 1, dtype=np.int),
                "m": grating_order,
                "header": hdr,
            }
            if sn_hdus is not None:
                sn = sn_hdus[0].data[10]
                unc = np.abs(flux / sn)
                uncertainty = StdDevUncertainty(unc)
                mask = np.isnan(flux) | np.isnan(uncertainty.array)
            else:
                uncertainty = None
                mask = np.isnan(flux)

            super().__init__(
                spectral_axis=lamb.to(u.Angstrom),
                flux=flux,
                mask=mask,
                wcs=None,
                uncertainty=uncertainty,
                meta=meta_dict,
                **kwargs,
            )
        else:
            super().__init__(*args, **kwargs)

    @property
    def site_name(self):
        """Which pipeline does this spectrum originate from?"""
        # TODO: add a check lookup dictionary for other telescopes
        # to ensure astropy compatibility
        return self.meta["header"]["TELESCOP"]

    @property
    def RA(self):
        """The right ascension from header files"""
        return self.meta["header"]["OBJRA"] * u.deg

    @property
    def DEC(self):
        """The declination from header files"""
        return self.meta["header"]["OBJDEC"] * u.deg

    @property
    def astropy_time(self):
        """The astropy time based on the header"""
        mjd = self.meta["header"]["MJD-OBS"]
        return Time(mjd, format="mjd", scale="utc")


class IGRINSSpectrumList(EchelleSpectrumList):
    r"""
    An enhanced container for a list of IGRINS spectral orders

    """

    def __init__(self, *args, **kwargs):
        self.normalization_order_index = 14
        super().__init__(*args, **kwargs)

    @staticmethod
    def read(file, wavefile=None, precache_hdus=True):
        """Read in a SpectrumList from a file

        Parameters
        ----------
        file : (str)
            A path to a reduced IGRINS spectrum from plp
        wafeile : (str)

        """
        assert (".spec_a0v.fits" in file) or (".spec.fits" in file)
        hdus = fits.open(file, memmap=False)

        sn_file = file[:19] + "sn.fits"
        sn_hdus = fits.open(sn_file, memmap=False)
        cached_hdus = [hdus, sn_hdus]
        if wavefile is not None:
            wave_hdus = fits.open(wavefile, memmap=False)
            cached_hdus.append(wave_hdus)

        #n_orders, n_pix = hdus["WAVELENGTH"].data.shape
        n_orders, n_pix = hdus[0].data.shape

        list_out = []
        for i in range(n_orders):
            spec = IGRINSSpectrum(file=file, wavefile=wavefile, order=i, cached_hdus=cached_hdus)
            list_out.append(spec)
        return IGRINSSpectrumList(list_out)
