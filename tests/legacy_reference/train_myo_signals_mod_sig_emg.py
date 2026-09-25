"""Verbatim copy of feature functions from Train_Myo_Signals/mod_sig_emg.py.

Source: https://github.com/Calima94/Train_Myo_Signals (commit 20fca8a), Apache-2.0.
Kept byte-for-byte (except this header and imports) as the golden reference
for tests/test_features_equivalence.py. Do not edit or reformat.
"""
# ruff: noqa
# fmt: off
import math

import numpy as np
import pywt
from scipy import signal

def standardize_classes(classes, time_between_captures_of_samples, window_time):
    n_of_samples = window_time // time_between_captures_of_samples
    for i, j in enumerate(classes):
        lenght_ = int((len(j) // n_of_samples) * n_of_samples)
        # classes[i] = classes[i].iloc[:lenght_, :8]
        classes[i] = classes[i].iloc[:lenght_, :-1]
    return classes


def to_numpy_func(classes):
    for i, j in enumerate(classes):
        classes[i] = j.to_numpy()
    classes = np.array(classes, dtype=object)

    return classes


def sample_classes_(classes, time_between_captures_of_samples, window_time, n_of_channels_and_category):
    n_of_classes = len(classes)
    n_samples = int(window_time / time_between_captures_of_samples)
    class_mod_f = []
    for i, j in enumerate(classes):
        len_ = int(len(j) / n_samples)
        class_mod_ = np.zeros([len_, n_samples, n_of_channels_and_category])
        for k in range(len_):
            for l in range(n_samples):
                class_mod_[k, l, :] = classes[i][l + k * n_samples][:]
        class_mod_f.append(class_mod_)
    class_mod_f = np.array(class_mod_f, dtype=object)

    return class_mod_f


def filter_signal(class_mod_, sos, n_of_channels_and_category):
    for i, j in enumerate(class_mod_):
        # l_class_ = len(class_mod_[i])
        for k, l in enumerate(class_mod_[i]):
            for m in range(n_of_channels_and_category):
                # signal_mod = class_mod_[i][k, :, l]
                # signal_mod = filter_iir(sig=signal_mod, sos=sos)
                class_mod_[i][k, :, m] = signal.sosfilt(sos, class_mod_[i][k, :, m])

                # class_mod_[i][k, :, l] = signal_mod
    return class_mod_


def wav_filter(signal, filter_to_use, levels_to_use, layers_to_catch):
    a = 1
    Coeffs = pywt.wavedec(signal, filter_to_use, level=levels_to_use)

    for i in range(1, -1, -(levels_to_use + 1)):
        if -i not in layers_to_catch:
            Coeffs[i] = np.zeros_like(Coeffs[i])
    Rec = pywt.waverec(Coeffs, filter_to_use)
    return Rec


def select_wavelet_layer_x(class_mod_, filter_to_use, levels_to_use,
                           layers_to_catch, n_of_channels_and_category):
    for i, j in enumerate(class_mod_):
        # l_class_ = int(len(class_mod_[i]))
        for k, l in enumerate(class_mod_[i]):
            for m in range(n_of_channels_and_category):
                # signal_mod = class_mod_[i][k, :, m]
                class_mod_[i][k, :, m] = wav_filter(signal=class_mod_[i][k, :, m],
                                                    filter_to_use=filter_to_use,
                                                    levels_to_use=levels_to_use,
                                                    layers_to_catch=layers_to_catch
                                                    )
                # class_mod_[i][k, :, l] = signal_mod
    return class_mod_


def m_mav_values_(class_mod_, time_between_captures_of_samples, window_time, n_of_channels_and_category):
    mav_table_ = []
    n_of_samples = int(window_time / time_between_captures_of_samples)

    for i, j in enumerate(class_mod_):
        acum_x = 0
        l_class_ = int(len(j))
        s = [l_class_, n_of_channels_and_category]
        m_class_ = np.zeros(s)
        for k in range(l_class_):
            for l in range(n_of_channels_and_category):
                for m in range(n_of_samples):
                    acum_x += abs(j[k, m, l]) / n_of_samples
                m_class_[k, l] = acum_x
                acum_x = 0
        mav_table_.append(m_class_)
    mav_table_ = np.array(mav_table_, dtype=object)
    return mav_table_


def m_rms_values_(class_mod_, time_between_captures_of_samples, window_time, n_of_channels_and_category):
    rms_table_ = []
    n_of_samples = int(window_time / time_between_captures_of_samples)

    for i, j in enumerate(class_mod_):
        acum_x = 0
        l_class_ = int(len(j))
        s = [l_class_, n_of_channels_and_category]
        m_class_ = np.zeros(s)
        for k in range(l_class_):
            for l in range(n_of_channels_and_category):
                for m in range(n_of_samples):
                    acum_x += ((j[k, m, l]) ** 2) / n_of_samples
                m_class_[k, l] = math.sqrt(acum_x)
                acum_x = 0
        rms_table_.append(m_class_)
    rms_table_ = np.array(rms_table_, dtype=object)
    return rms_table_


def matrix_m(type_matrix, class_mod_, time_between_captures_of_samples, window_time, n_of_channels_and_category):
    if type_matrix == "rms":
        m_matrix_ = m_rms_values_(class_mod_, time_between_captures_of_samples, window_time, n_of_channels_and_category)
    elif type_matrix == "mav":
        m_matrix_ = m_mav_values_(class_mod_, time_between_captures_of_samples, window_time, n_of_channels_and_category)
    return m_matrix_
