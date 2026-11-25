"""Run: python3 test_logic.py"""
import importlib.util
import pathlib

p = pathlib.Path(__file__).parent / "custom_components/nursery_climate/logic.py"
spec = importlib.util.spec_from_file_location("logic", p)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)
decide, slope = logic.decide, logic.slope

# Same numbers the old automation would produce (band 67-70.5, mid 68.75, Kp 2.5, Kd 8).
assert decide(72, 67, 67, 70.5, 2.5, 8, 0) == ("cool", 58.9, "cooling")
assert decide(66, 67, 67, 70.5, 2.5, 8, 0) == ("heat", 73.9, "heating")
assert decide(68.75, 67, 67, 70.5, 2.5, 8, 0.1) == (None, 66.2, "in_band")
assert decide(80, 67, 67, 70.5, 2.5, 8, 0)[1] == 55  # clamped low
assert decide(60, 80, 67, 70.5, 2.5, 8, 0)[1] == 85  # clamped high

assert slope([(0, 70), (60, 70.5)], 60) == 0.5
assert abs(slope([(0, 60), (400, 70), (460, 70.2)], 460) - 0.2) < 1e-9  # old sample ignored
assert slope([(0, 70), (10, 71)], 10) == 0.0  # under 30 s of data
assert slope([(0, 70)], 0) == 0.0
accept = logic.accept
assert accept(70.4, 70.0, None, 3) == (True, None)  # normal drift
assert accept(84.0, 70.0, None, 3) == (False, 84.0)  # spike held back
assert accept(70.2, 70.0, 84.0, 3) == (True, None)  # back to normal: spike dropped
assert accept(83.5, 70.0, 84.0, 3) == (True, None)  # confirmed by a second reading
assert accept(84.0, None, None, 3) == (True, None)  # nothing to compare against
assert accept(84.0, 70.0, None, 0) == (True, None)  # filter off

hand_back = logic.hand_back
assert hand_back("auto", 65, 68, "cool") == "heat"  # house cold: heat back up
assert hand_back("auto", 72, 68, "heat") == "cool"  # house warm: cool back down
assert hand_back("auto", 67.5, 68, "cool") == "cool"  # within the deadband: keep the mode
assert hand_back("auto", 68.5, 68, "heat_cool") == "cool"  # not heat/cool: pick by side
assert hand_back("auto", 68, 68, "heat_cool") == "heat"
assert hand_back("auto", None, 68, "cool") is None  # no house reading: leave the mode
assert hand_back("heat", 75, 68, "cool") == "heat"  # fixed choices win
assert hand_back("cool", 60, 68, "heat") == "cool"
assert hand_back("off", 65, 68, "heat") == "off"
for choice in ("auto", "heat", "cool", "off"):
    assert hand_back(choice, 65, 68, "off") is None  # already off: someone meant it
    assert hand_back(choice, 65, 68, "unavailable") is None
print("ok")
