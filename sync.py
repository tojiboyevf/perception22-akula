from ekf import EKFarc
import numpy as np
import matplotlib.pyplot as plt
import argparse
import os
from termcolor import colored

def forward_kinematics(params: dict, state: np.ndarray, odometry: np.ndarray) -> np.ndarray:
    """
    Forward kinematics for differential platform
    Arc Kinematic motion model (Prob.Rob.Ch5.3)
    Assumption: motion consists of arcs

    Arc length = k * (V1 + V2) / 2
    Arc angle = k * (V1 - V2) / l
    k = 2 * pi * r / counts_2pi

    angle_wheel (scalar) = counts / counts_per_rotation * 2 * pi
    angle_robot (scalar) = angle_wheel * r / R (R - rotation radius (L))

    :param params: Dict, robot geometry parameters
    :param state: Array-like object (1x3), robot current state [x, y, theta]
    :param odometry: Array-like object (1x2), ticks from odometry [right, left]
    """
    assert state.shape == (3,)
    assert odometry.shape == (2,)
    assert params.get('diag_length')
    assert params.get('wheel_radius')
    assert params.get('counts_per_rotation')

    l = params['diag_length']
    r = params['wheel_radius']
    counts_2pi = params['counts_per_rotation']
    x, y, th = state

    k = 2 * np.pi * r / counts_2pi
    d_len_right = odometry[0] * k
    d_len_left = odometry[1] * k
    d_len = (d_len_right + d_len_left) / 2
    d_angle = (d_len_right - d_len_left) / l

    if d_angle != 0:
        d_state = np.array([d_len/d_angle * (-np.sin(th) + np.sin(th + d_angle)),
                            d_len/d_angle * (np.cos(th) - np.cos(th + d_angle)),
                            d_angle])
    else:
        d_state = np.array([d_len * np.cos(th),
                            d_len * np.sin(th),
                            d_angle])

    return d_state


def aplly_EKF(args):
    source_observations = args.source_observations
    source_actions = args.source_actions

    obs = open(source_observations, 'r', encoding='utf-8')
    acts = open(source_actions, 'r', encoding='utf-8')

    input_filename = args.input_filename
    f_in = open(input_filename, 'r')

    # metres
    params = {'diag_length': 0.490,
              'wheel_radius': 0.130,
              'counts_per_rotation': 2394}

    # find first observation
    ts_obs_prev, left_obs_prev, right_obs_prev = list(map(int, obs.readline().split()))
    while True:
        ts_obs, left_obs, right_obs = list(map(int, obs.readline().split()))

        if (left_obs - left_obs_prev) or (right_obs - right_obs_prev):
            break
        
        ts_obs_prev, left_obs_prev, right_obs_prev = ts_obs, left_obs, right_obs
    ts_obs_0 = ts_obs_prev
    ts_obs_prev = 0
    ts_obs -= ts_obs_0

    ts_acts_prev, left_acts_prev, right_acts_prev = list(map(int, acts.readline().split()))
    ts_acts_0 = ts_acts_prev
    ts_acts_prev = 0

    ts = 0

    state_initial = np.array([[0.], [0.], [0.]])
    sigma_initial = np.array([[0., 0., 0.],
                              [0., 0., 0.],
                              [0., 0., 0.]])
    alphas = np.array([0, 0, 0, 0])
    d = 0.490
    r = 0.130
    counts_2pi = 2394
    k = 2 * np.pi * r / counts_2pi
    Q = np.array([[1, 0],
                  [0, 1]])

    ekf = EKFarc(state_initial, sigma_initial, alphas, d, k, Q)
    x = []
    y = []
    th = []

    k = 2 * np.pi * r / counts_2pi
    d_l = (4283919143 - 4283826615) / (1000 * 26.359 * 223)
    d_r = (4288936710 - 4288840803) / (1000 * 26.359 * 223)

    while True:
        acts_line = acts.readline()
        if not acts_line:
            break
        ts_acts, left_acts, right_acts = list(map(int, acts_line.split()))
        ts_acts -= ts_acts_0

        v = (d_r * right_acts_prev + d_l * left_acts_prev) / 2 * k
        w = (d_r * right_acts_prev - d_l * left_acts_prev) / d * k
        
        while ts_obs <= ts_acts:
            ekf.predict([v, w], (ts_obs - ts)/1000)
            ekf.update(np.array([[(left_obs-left_obs_prev)], [(right_obs-right_obs_prev)]]))
            ts = ts_obs

            x.append(ekf.mu[0][0])
            y.append(ekf.mu[1][0])
            th.append(ekf.mu[2][0])

            obs_line = obs.readline()
            if obs_line == '\n':
                ts_obs = np.inf
                break
            
            ts_obs_prev, left_obs_prev, right_obs_prev = ts_obs, left_obs, right_obs
            ts_obs, left_obs, right_obs = list(map(int, obs_line.split()))
            ts_obs -= ts_obs_0

        ekf.predict([v, w], (ts_acts - ts)/1000)
        ts = ts_acts

        ts_acts_prev, left_acts_prev, right_acts_prev = ts_acts, left_acts, right_acts

    obs.close()
    acts.close()


    # initial state
    state = np.array([0., 0., 0.])

    timestamp_last, left, right = list(map(int, f_in.readline().split()))

    x_in = [state[0]]
    y_in = [state[1]]
    th_in = [state[2]]

    # ticks (counts on every wheel)
    folder_name_plot_path = args.folder_path_output
    file_name_plot_path = os.path.join(folder_name_plot_path, 'path.png')
    while True:
        inp = list(map(int, f_in.readline().split()))
        if not inp:
            break
        timestamp = inp[0]
        d_time = (timestamp - timestamp_last) / 1000
        timestamp_last = timestamp
        odometry = np.array([right*d_time*d_r, left*d_time*d_l])
        left = inp[1]
        right = inp[2]
        d_state = forward_kinematics(params, state, odometry)
        state = state + d_state
        x_in.append(state[0])
        y_in.append(state[1])
        th_in.append(state[2])

    f_in.close()

    plt.figure()
    plt.plot(x, y)
    plt.grid()
    plt.plot(np.array(x_in), np.array(y_in))
    plt.legend(['ekf', 'Input'])
    plt.savefig(file_name_plot_path, dpi=400)
    print(colored('saved to:', 'blue', attrs=['bold']), file_name_plot_path)
    plt.show()


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    
    parser.add_argument('-src_obs',
                        type=str,
                        dest='source_observations',
                        action='store',
                        default='./data/obs06.txt',
                        help="Path to observation file")

    parser.add_argument('-src_act',
                        type=str,
                        dest='source_actions',
                        action='store',
                        default='./raw_data/input_log06.txt',
                        help="Path to actions file")

    parser.add_argument('-inp_file',
                        type=str,
                        dest='input_filename',
                        action='store',
                        default='./raw_data/input_log06.txt')

    parser.add_argument('-save_to',
                        type=str,
                        dest='folder_path_output',
                        action='store',
                        default='./output')

    args = parser.parse_args()
    aplly_EKF(args)
