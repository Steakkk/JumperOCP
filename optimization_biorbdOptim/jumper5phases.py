from time import time

import biorbd

from biorbd_optim import (
    Instant,
    OptimalControlProgram,
    Constraint,
    Objective,
    ProblemType,
    BidirectionalMapping,
    Mapping,
    StateTransition,
    Bounds,
    QAndQDotBounds,
    InitialConditions,
    ShowResult,
    Data,
    PlotType,
)

# def constraint_2c_to_1c_transition(ocp, nlp, t, x, u, p):
#     val = ocp.nlp[0]["contact_forces_func"](x[0], u[0], p)[[2, 5], -1]
#     return val


def from_2contacts_to_1(ocp, nlp, t, x, u, p):
    return ocp.nlp[0]["contact_forces_func"](x[0], u[0], p)[[2, 5], -1]


def from_1contact_to_0(ocp, nlp, t, x, u, p):
    return ocp.nlp[1]["contact_forces_func"](x[0], u[0], p)[:, -1]


def from_0contact_to_1(ocp, nlp, t, x, u, p):
    nbQ_reduced = nlp["nbQ"]
    q_reduced = nlp["X"][0][:nbQ_reduced]
    q = nlp["q_mapping"].expand.map(q_reduced)
    toeD_marker_z = nlp["model"].marker(q, 2).to_mx()[2]
    return (
        toeD_marker_z + 0.77865438
    )  # -0.77865438 is the value returned with Eigen by the 3rd dim. of toeD_marker CoM at pose_at_first_node


def from_1contact_to_2(ocp, nlp, t, x, u, p):
    nbQ_reduced = nlp["nbQ"]
    q_reduced = nlp["X"][0][:nbQ_reduced]
    q = nlp["q_mapping"].expand.map(q_reduced)
    talD_marker_z = nlp["model"].marker(q, 3).to_mx()[2]
    return (
        talD_marker_z + 0.77865829
    )  # -0.77865829 is the value returned with Eigen by the 3rd dim. of toeD_marker CoM at pose_at_first_node


# def phase_transition_1c_to_2c(nlp_pre, nlp_post):
#     nbQ = nlp_post["nbQ"]
#     q_reduced = nlp_post["X"][0][:nbQ]
#     q = nlp_post["q_mapping"].expand.map(q_reduced)
#     talD_marker = nlp_post["model"].marker(q, 3).to_mx()
#     return talD_marker


def custom_func_anatomical_constraint(ocp, nlp, t, x, u, p):
    val = x[0][7:14]
    return val


def prepare_ocp(model_path, phase_time, number_shooting_points, use_symmetry=True):
    # --- Options --- #
    # Model path
    biorbd_model = [biorbd.Model(elt) for elt in model_path]

    nb_phases = len(biorbd_model)
    torque_activation_min, torque_activation_max, torque_activation_init = -1, 1, 0

    if use_symmetry:
        q_mapping = BidirectionalMapping(
            Mapping([0, 1, 2, -1, 3, -1, 3, 4, 5, 6, 4, 5, 6], [5]), Mapping([0, 1, 2, 4, 7, 8, 9])
        )
        q_mapping = q_mapping, q_mapping, q_mapping, q_mapping, q_mapping
        tau_mapping = BidirectionalMapping(
            Mapping([-1, -1, -1, -1, 0, -1, 0, 1, 2, 3, 1, 2, 3], [5]), Mapping([4, 7, 8, 9])
        )
        tau_mapping = tau_mapping, tau_mapping, tau_mapping, tau_mapping, tau_mapping

    else:
        q_mapping = BidirectionalMapping(
            Mapping([i for i in range(biorbd_model[0].nbQ())]), Mapping([i for i in range(biorbd_model[0].nbQ())])
        )
        q_mapping = q_mapping, q_mapping, q_mapping, q_mapping, q_mapping
        tau_mapping = q_mapping

    # Add objective functions
    objective_functions = (
        (),
        (
            {"type": Objective.Mayer.MINIMIZE_PREDICTED_COM_HEIGHT, "weight": -1},
            # {"type": Objective.Lagrange.MINIMIZE_TORQUE, "weight": -1 / 100},
        ),
        (
            # {"type": Objective.Lagrange.MINIMIZE_TORQUE, "weight": -1 / 100},
        ),
        (
            # {"type": Objective.Lagrange.MINIMIZE_TORQUE, "weight": -1 / 100},
        ),
        (
            # {"type": Objective.Lagrange.MINIMIZE_TORQUE, "weight": -1 / 100},
        ),
    )

    # Dynamics
    problem_type = (
        {"type": ProblemType.TORQUE_ACTIVATIONS_DRIVEN_WITH_CONTACT},
        {"type": ProblemType.TORQUE_ACTIVATIONS_DRIVEN_WITH_CONTACT},
        {"type": ProblemType.TORQUE_ACTIVATIONS_DRIVEN},
        {"type": ProblemType.TORQUE_ACTIVATIONS_DRIVEN_WITH_CONTACT},
        {"type": ProblemType.TORQUE_ACTIVATIONS_DRIVEN_WITH_CONTACT},
    )

    constraints_first_phase = []
    constraints_second_phase = []
    constraints_third_phase = []
    constraints_fourth_phase = []
    constraints_fifth_phase = []

    # Positivity constraints of the normal component of the reaction forces
    contact_axes = (1, 2, 4, 5)
    for i in contact_axes:
        constraints_first_phase.append(
            {
                "type": Constraint.CONTACT_FORCE_INEQUALITY,
                "direction": "GREATER_THAN",
                "instant": Instant.ALL,
                "contact_force_idx": i,
                "boundary": 0,
            }
        )
        constraints_fifth_phase.append(
            {
                "type": Constraint.CONTACT_FORCE_INEQUALITY,
                "direction": "GREATER_THAN",
                "instant": Instant.ALL,
                "contact_force_idx": i,
                "boundary": 0,
            }
        )
    contact_axes = (1, 3)
    for i in contact_axes:
        constraints_second_phase.append(
            {
                "type": Constraint.CONTACT_FORCE_INEQUALITY,
                "direction": "GREATER_THAN",
                "instant": Instant.ALL,
                "contact_force_idx": i,
                "boundary": 0,
            }
        )
        constraints_fourth_phase.append(
            {
                "type": Constraint.CONTACT_FORCE_INEQUALITY,
                "direction": "GREATER_THAN",
                "instant": Instant.ALL,
                "contact_force_idx": i,
                "boundary": 0,
            }
        )

    # Non-slipping constraints
    # N.B.: Application on only one of the two feet is sufficient, as the slippage cannot occurs on only one foot.
    constraints_first_phase.append(
        {
            "type": Constraint.NON_SLIPPING,
            "instant": Instant.ALL,
            "normal_component_idx": (1, 2),
            "tangential_component_idx": 0,
            "static_friction_coefficient": 0.5,
        }
    )
    constraints_second_phase.append(
        {
            "type": Constraint.NON_SLIPPING,
            "instant": Instant.ALL,
            "normal_component_idx": 1,
            "tangential_component_idx": 0,
            "static_friction_coefficient": 0.5,
        }
    )
    constraints_fourth_phase.append(
        {
            "type": Constraint.NON_SLIPPING,
            "instant": Instant.ALL,
            "normal_component_idx": 1,
            "tangential_component_idx": 0,
            "static_friction_coefficient": 0.5,
        }
    )
    constraints_fifth_phase.append(
        {
            "type": Constraint.NON_SLIPPING,
            "instant": Instant.ALL,
            "normal_component_idx": (1, 2),
            "tangential_component_idx": 0,
            "static_friction_coefficient": 0.5,
        }
    )

    # Custom constraints for contact forces at transitions
    constraints_second_phase.append(
        {"type": Constraint.CUSTOM, "function": from_2contacts_to_1, "instant": Instant.START}
    )
    constraints_third_phase.append(
        {"type": Constraint.CUSTOM, "function": from_1contact_to_0, "instant": Instant.START}
    )
    constraints_fourth_phase.append(
        {"type": Constraint.CUSTOM, "function": from_0contact_to_1, "instant": Instant.START}
    )
    constraints_fifth_phase.append(
        {"type": Constraint.CUSTOM, "function": from_1contact_to_2, "instant": Instant.START}
    )

    if not use_symmetry:
        first_dof = (3, 4, 7, 8, 9)
        second_dof = (5, 6, 10, 11, 12)
        coef = (-1, 1, 1, 1, 1)
        for i in range(len(first_dof)):
            for elt in [
                constraints_first_phase,
                constraints_second_phase,
                constraints_third_phase,
                constraints_fourth_phase,
                constraints_fifth_phase,
            ]:
                elt.append(
                    {
                        "type": Constraint.PROPORTIONAL_STATE,
                        "instant": Instant.ALL,
                        "first_dof": first_dof[i],
                        "second_dof": second_dof[i],
                        "coef": coef[i],
                    }
                )
    constraints = (
        constraints_first_phase,
        constraints_second_phase,
        constraints_third_phase,
        constraints_fourth_phase,
        constraints_fifth_phase,
    )
    for i, constraints_phase in enumerate(constraints):
        constraints_phase.append({"type": Constraint.TIME_CONSTRAINT, "minimum": time_min[i], "maximum": time_max[i]})

    # State transitions
    state_transitions = ({"type": StateTransition.IMPACT, "phase_pre_idx": 2},)

    # Path constraint
    if use_symmetry:
        nb_q = q_mapping[0].reduce.len
        nb_qdot = nb_q
        pose_at_first_node = [0, 0, -0.5336, 1.4, 0.8, -0.9, 0.47]
    else:
        nb_q = q_mapping[0].reduce.len
        nb_qdot = nb_q
        pose_at_first_node = [0, 0, -0.5336, 0, 1.4, 0, 1.4, 0.8, -0.9, 0.47, 0.8, -0.9, 0.47]

    # Initialize X_bounds
    X_bounds = [QAndQDotBounds(biorbd_model[i], all_generalized_mapping=q_mapping[i]) for i in range(nb_phases)]
    X_bounds[0].min[:, 0] = pose_at_first_node + [0] * nb_qdot
    X_bounds[0].max[:, 0] = pose_at_first_node + [0] * nb_qdot
    X_bounds[4].min[:, -1] = pose_at_first_node + [0] * nb_qdot
    X_bounds[4].max[:, -1] = pose_at_first_node + [0] * nb_qdot

    # Initial guess
    X_init = [InitialConditions(pose_at_first_node + [0] * nb_qdot) for i in range(nb_phases)]

    # Define control path constraint
    U_bounds = [
        Bounds(
            min_bound=[torque_activation_min] * tau_m.reduce.len, max_bound=[torque_activation_max] * tau_m.reduce.len
        )
        for tau_m in tau_mapping
    ]

    U_init = [InitialConditions([torque_activation_init] * tau_m.reduce.len) for tau_m in tau_mapping]
    # ------------- #

    return OptimalControlProgram(
        biorbd_model,
        problem_type,
        number_shooting_points,
        phase_time,
        X_init,
        U_init,
        X_bounds,
        U_bounds,
        objective_functions=objective_functions,
        constraints=constraints,
        q_mapping=q_mapping,
        q_dot_mapping=q_mapping,
        tau_mapping=tau_mapping,
        state_transitions=state_transitions,
    )


def plot_CoM(x, model_path):
    m = biorbd.Model(model_path)
    q_mapping = BidirectionalMapping(
        Mapping([0, 1, 2, -1, 3, -1, 3, 4, 5, 6, 4, 5, 6], [5]), Mapping([0, 1, 2, 4, 7, 8, 9])
    )
    q_reduced = x[:7, :]
    q_expanded = q_mapping.expand.map(q_reduced)
    from casadi import Function, MX
    import numpy as np

    q_sym = MX.sym("q", m.nbQ(), 1)
    CoM_func = Function("Compute_CoM", [q_sym], [m.CoM(q_sym).to_mx()], ["q"], ["CoM"],).expand()
    CoM = np.array(CoM_func(q_expanded[:, :]))
    return CoM[2]


def plot_CoM_dot(x, model_path):
    m = biorbd.Model(model_path)
    q_mapping = BidirectionalMapping(
        Mapping([0, 1, 2, -1, 3, -1, 3, 4, 5, 6, 4, 5, 6], [5]), Mapping([0, 1, 2, 4, 7, 8, 9])
    )
    q_reduced = x[:7, :]
    qdot_reduced = x[7:, :]
    q_expanded = q_mapping.expand.map(q_reduced)
    qdot_expanded = q_mapping.expand.map(qdot_reduced)
    from casadi import Function, MX
    import numpy as np

    q_sym = MX.sym("q", m.nbQ(), 1)
    qdot_sym = MX.sym("q_dot", m.nbQdot(), 1)
    CoM_dot_func = Function(
        "Compute_CoM_dot", [q_sym, qdot_sym], [m.CoMdot(q_sym, qdot_sym).to_mx()], ["q", "q_dot"], ["CoM_dot"],
    ).expand()
    CoM_dot = np.array(CoM_dot_func(q_expanded[:, :], qdot_expanded[:, :]))
    return CoM_dot[2]


def run_and_save_ocp(model_path, phase_time, number_shooting_points):
    ocp = prepare_ocp(
        model_path=model_path, phase_time=phase_time, number_shooting_points=number_shooting_points, use_symmetry=True
    )
    for i in range(len(model_path)):
        ocp.add_plot("CoM", lambda x, u, p: plot_CoM(x, model_path[i]), phase_number=i, plot_type=PlotType.PLOT)
        ocp.add_plot("CoM_dot", lambda x, u, p: plot_CoM_dot(x, model_path[i]), phase_number=i, plot_type=PlotType.PLOT)
    sol = ocp.solve(options_ipopt={"hessian_approximation": "exact", "max_iter": 1000}, show_online_optim=True)

    OptimalControlProgram.save(ocp, sol, "../Results/jumper5phases_exact_sol")


if __name__ == "__main__":
    model_path = (
        "../models/jumper2contacts.bioMod",
        "../models/jumper1contacts.bioMod",
        "../models/jumper1contacts.bioMod",
        "../models/jumper1contacts.bioMod",
        "../models/jumper2contacts.bioMod",
    )
    time_min = [0.1, 0.3, 0.2, 0.1, 0.1]
    time_max = [0.4, 0.6, 2, 0.4, 0.4]
    phase_time = [0.2, 0.4, 1, 0.3, 0.3]
    number_shooting_points = [20, 20, 20, 20, 20]

    tic = time()

    run_and_save_ocp(model_path, phase_time=phase_time, number_shooting_points=number_shooting_points)
    ocp, sol = OptimalControlProgram.load("../Results/jumper5phases_sol.bo")

    # ocp = prepare_ocp(model_path=model_path, phase_time=phase_time, number_shooting_points=number_shooting_points, use_symmetry=True)
    # sol = ocp.solve(show_online_optim=False, options_ipopt={"hessian_approximation": "limited-memory", "max_iter": 2})

    # --- Show results --- #
    param = Data.get_data(ocp, sol["x"], get_states=False, get_controls=False, get_parameters=True)
    print(
        f"The optimized phases times are: {param['time'][0, 0]}s, {param['time'][1, 0]}s, {param['time'][2, 0]}s, {param['time'][3, 0]}s and {param['time'][4, 0]}s."
    )

    toc = time() - tic
    print(f"Time to solve : {toc}sec")

    result = ShowResult(ocp, sol)
    result.graphs()
    result.animate(nb_frames=61)
