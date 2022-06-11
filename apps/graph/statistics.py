import numpy as np
import math


# 폴더가 한글, 한자 등 영어 외 문자로 계정 폴더 사용 시 주의 : temp 폴더 경로 변경할 것
import scipy.signal

class HighPassFilter(object):
    @staticmethod
    def get_highpass_coefficients(lowcut, sample_rate, order=5):
        nyq = 0.5 * sample_rate
        low = lowcut / nyq
        b, a = scipy.signal.butter(order, [low], btype='highpass')
        return b, a

    @staticmethod
    def run_highpass_filter(data, lowcut, sample_rate, order=5):
        if lowcut >= sample_rate / 2.0:
            return data * 0.0
        b, a = HighPassFilter.get_highpass_coefficients(lowcut, sample_rate, order=order)
        y = scipy.signal.filtfilt(b, a, data, padtype='even')
        return y

    @staticmethod
    def perform_hpf_filtering(data, sample_rate, hpf=3):
        if hpf == 0:
            return data
        data[0:6] = data[13:7:-1]  # skip compressor settling
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=3,
            sample_rate=sample_rate,
            order=1,
        )
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=int(hpf),
            sample_rate=sample_rate,
            order=2,
        )
        return data

    # transformed = data => rms | kurtosis
    # valuesX, valuesY, valuesZ, fRangesX, fRangesY, fRangesZ, sampleRatesX, sampleRatesY, sampleRatesZ, hpf=3
    @staticmethod
    def hpf_loop(**data):
        transformed = []
        x_valid = data.get('valuesX')
        y_valid = data.get('valuesY')
        z_valid = data.get('valuesZ')
        x_range_valid = data.get('fRangesX')
        y_range_valid = data.get('fRangesY')
        z_range_valid = data.get('fRangesZ')
        x_sample_valid = data.get('sampleRatesX')
        y_sample_valid = data.get('sampleRatesY')
        z_sample_valid = data.get('sampleRatesZ')

        x_flag = y_flag = z_flag = 1
        if x_valid is None or not x_valid or len(x_valid) == 0:
            x_flag = 0
        if y_valid is None or not y_valid or len(y_valid) == 0:
            y_flag = 0
        if z_valid is None or not z_valid or len(z_valid) == 0:
            z_flag = 0

        if x_flag == 1:
            v = x_valid
            f = x_range_valid
            s = x_sample_valid

            for i in range(len(f)):
                v[i] = [d / 512.0 * f[i] for d in v[i]]
                v[i] = HighPassFilter.perform_hpf_filtering(
                    data=v[i],
                    sample_rate=s[i],
                    hpf=6
                )
                transformed.append(v[i])
                # print(f'transformed : {transformed}')

            # print(f'transformed done : {transformed}')
            return transformed

        if y_flag == 1:
            v = y_valid
            f = y_range_valid
            s = y_sample_valid

            # print(f'len(f) = {len(f)}')

            for i in range(len(f)):
                v[i] = [d / 512.0 * f[i] for d in v[i]]
                v[i] = HighPassFilter.perform_hpf_filtering(
                    data=v[i],
                    sample_rate=s[i],
                    hpf=6
                )
                transformed.append(v[i])
                # print(f'y_transformed : {transformed}')

            return transformed

        if z_flag == 1:
            for (v, f, s) in list(zip([z_valid], [z_range_valid], [z_sample_valid])):

                # print(f'len(f) = {len(f)}')

                for i in range(len(f)):
                    try:
                        v[i] = [d / 512.0 * f[i] for d in v[i]]
                        v[i] = HighPassFilter.perform_hpf_filtering(
                            data=v[i],
                            sample_rate=s[i],
                            hpf=6
                        )
                        transformed.append(v[i])

                    except TypeError:
                        transformed.append(v[i])

            return transformed

        if x_flag == y_flag == z_flag == 1:
            for (v, f, s) in list(zip([x_valid, y_valid, z_valid], [x_range_valid, y_range_valid, z_range_valid],
                                      [x_sample_valid, y_sample_valid, z_sample_valid])):

                # print(f'len(f) = {len(f)}')

                for i in range(len(f)):
                    try:
                        v[i] = [d / 512.0 * f[i] for d in v[i]]
                        v[i] = HighPassFilter.perform_hpf_filtering(
                            data=v[i],
                            sample_rate=s[i],
                            hpf=6
                        )
                        transformed.append(v[i])

                    except TypeError:
                        transformed.append(v[i])

            return transformed

        else:
            return None

    @staticmethod
    def rms(ndarray):
        return np.sqrt(np.mean(ndarray ** 2))


class FourierTransform(object):

    @staticmethod
    def perform_fft_windowed(signal, fs, win_size, n_overlap, window, detrend=True, mode='lin'):
        assert (n_overlap < win_size)
        assert (mode in ('magnitudeRMS', 'magnitudePeak', 'lin', 'log'))

        # Compose window and calculate 'coherent gain scale factor'
        w = scipy.signal.get_window(window, win_size)
        """
         http://www.bores.com/courses/advanced/windows/files/windows.pdf
         Bores signal processing: "FFT window functions: Limits on FFT analysis"
         F. J. Harris, "On the use of windows for harmonic analysis with the
         discrete Fourier transform," in Proceedings of the IEEE, vol. 66, no. 1,
         pp. 51-83, Jan. 1978.
        
        """
        coherentGainScaleFactor = np.sum(w) / win_size

        # Zero-pad signal if smaller than window
        padding = len(w) - len(signal)
        if padding > 0:
            signal = np.pad(signal, (0, padding), 'constant')

        # Number of windows
        k = int(np.fix((len(signal) - n_overlap) / (len(w) - n_overlap)))

        # Calculate psd
        j = 0
        spec = np.zeros(len(w))
        for i in range(0, k):
            segment = signal[j:j + len(w)]
            if detrend is True:
                segment = scipy.signal.detrend(segment)
            win_data = segment * w
            # Calculate FFT, divide by sqrt(N) for power conservation,
            # and another sqrt(N) for RMS amplitude spectrum.
            fft_data = np.fft.fft(win_data, len(w)) / len(w)
            sq_abs_fft = abs(fft_data / coherentGainScaleFactor) ** 2
            spec = spec + sq_abs_fft
            j = j + len(w) - n_overlap

        # Scale for number of windows
        spec = spec / k

        # If signal is not complex, select first half
        if len(np.where(np.iscomplex(signal))[0]) == 0:
            stop = int(math.ceil(len(w) / 2.0))
            # Multiply by 2, except for DC and fmax. It is asserted that N is even.
            spec[1:stop - 1] = 2 * spec[1:stop - 1]
        else:
            stop = len(w)
        spec = spec[0:stop]
        freq = np.round(float(fs) / len(w) * np.arange(0, stop), 2)

        if mode == 'lin':  # Linear Power spectrum
            return spec, freq
        elif mode == 'log':  # Log Power spectrum
            return 10. * np.log10(spec), freq
        elif mode == 'magnitudeRMS':  # RMS Magnitude spectrum
            return np.sqrt(spec), freq
        elif mode == 'magnitudePeak':  # Peak Magnitude spectrum
            return np.sqrt(2. * spec), freq

