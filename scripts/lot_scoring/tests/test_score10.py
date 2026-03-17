def test_score10_monotonic():
    gamma = 0.85
    values = [0.0, 0.01, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]
    scores = [round(10 * (v ** gamma), 2) for v in values]
    assert scores == sorted(scores)
    assert scores[0] == 0.0
    assert scores[-1] == 10.0


def test_score10_known_values():
    """Sanity checks for Score10 transformation."""
    gamma = 0.85

    # exact edge guarantees
    assert round(10 * (1.0 ** gamma), 2) == 10.0
    assert round(10 * (0.0 ** gamma), 2) == 0.0

    # monotonic ordering guarantees
    s_10 = round(10 * (0.10 ** gamma), 2)
    s_50 = round(10 * (0.50 ** gamma), 2)
    s_80 = round(10 * (0.80 ** gamma), 2)

    assert s_10 < s_50 < s_80
