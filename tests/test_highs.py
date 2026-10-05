import highspy


def test_highs_solves_small_knapsack():
    values, weights, capacity = [10, 13, 7, 8], [5, 6, 3, 4], 10
    m = highspy.Highs()
    m.setOptionValue("output_flag", False)
    x = m.addVariables(range(4), lb=0, ub=1, type=highspy.HighsVarType.kInteger, name_prefix="x")
    m.addConstr(m.qsum(weights[i] * x[i] for i in range(4)) <= capacity)
    m.setObjective(m.qsum(values[i] * x[i] for i in range(4)), sense=highspy.ObjSense.kMaximize)
    m.run()
    assert m.getModelStatus() == highspy.HighsModelStatus.kOptimal
    assert round(m.getInfo().objective_function_value) == 21  # items 1 and 3
