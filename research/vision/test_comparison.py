"""Sanity checks for honest missing/duplicate counts in the comparison report."""
import unittest

from compare_backends import compare_reps


class ComparisonTests(unittest.TestCase):
    def test_missing_rep_does_not_improve_reported_coverage(self):
        truth = [dict(lifting_start=dict(time=2.), lifting_end=dict(time=3.)),
                 dict(lifting_start=dict(time=6.), lifting_end=dict(time=7.))]
        predicted = [dict(athlete=1, liftingStart=2., liftingEnd=3., lifting=1.)]
        result = compare_reps(truth, predicted)
        self.assertEqual(result["matchedReps"], 1)
        self.assertEqual(result["missingAnnotationReps"], [2])
        self.assertEqual(result["matchedBoundaryCount"], 2)
        self.assertEqual(result["annotatedBoundaryCount"], 4)
        self.assertEqual(result["matchedBoundaryMaeSeconds"], 0.)

    def test_duplicate_athlete_does_not_match_one_rep_twice(self):
        truth = [dict(lifting_start=dict(time=2.), lifting_end=dict(time=3.))]
        predicted = [dict(athlete=i, liftingStart=2., liftingEnd=3., lifting=1.) for i in (1, 2)]
        result = compare_reps(truth, predicted)
        self.assertEqual(result["matchedReps"], 1)
        self.assertEqual(len(result["unmatchedDetections"]), 1)

    def test_no_overlap_is_missing_not_low_boundary_error(self):
        result = compare_reps([dict(lifting_start=dict(time=2.), lifting_end=dict(time=3.))],
            [dict(athlete=1, liftingStart=10., liftingEnd=11., lifting=1.)])
        self.assertIsNone(result["matchedBoundaryMaeSeconds"])
        self.assertEqual(result["missingAnnotationReps"], [1])


if __name__ == "__main__":
    unittest.main()
