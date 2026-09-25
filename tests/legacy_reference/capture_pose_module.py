"""Verbatim copy of category logic from Capture_EMG_Data/pose_module.py.

Source: https://github.com/Calima94/Capture_EMG_Data (commit a125299), Apache-2.0;
base version by Alan Mendes (see THIRD_PARTY_NOTICES.md).
The two static methods of PoseDetector, dedented and without @staticmethod,
otherwise unchanged. Golden reference for tests/test_capture.py.
Do not edit or reformat.
"""
# ruff: noqa
# fmt: off
from collections import Counter


def test_cases_to_use(tests_init, angle, var, angles_to_test, categories_already_trained):
    """
    Test if the angle that is being measuring is valid to write At that moment in the csv file, if its true return
    "True" and its category,
    Otherwise return false and zero
    """
    for i in range(tests_init):
        if i not in categories_already_trained:
            if angles_to_test[i] + var > angle > angles_to_test[i] - var:
                return True, i + 1
    return False, 0


def check_if_num_samples_is_complete(emg_table, list_of_angles, num_of_samples_in_each_class, test,
                                     categories_already_trained):
    """
    Check if the angles in a category is complete, if True subtract the number of the tests and add the category
    that have already been trained
    """
    emg_mod = [i[-1] for i in emg_table]
    emg_mod.sort()
    values = Counter(emg_mod).values()
    for i, j in enumerate(values):
        if i not in categories_already_trained:
            if j >= num_of_samples_in_each_class:
                categories_already_trained.append(i)
                test -= 1
                print(f"Finished the category {list_of_angles[i]}")
    return test, categories_already_trained
