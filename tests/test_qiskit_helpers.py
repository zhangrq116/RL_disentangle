import itertools
import numpy as np
import sys
from typing import Literal

sys.path.append('..')
from src.quantum_env import QuantumEnv, rdm_2q_half
from src.quantum_state import phase_norm
from qiskit.helpers import *

np.random.seed(44)
np.set_printoptions(precision=6, suppress=True)


def observe_rdms(state):
    L = int(np.log2(state.size))
    shape = (1,) + (2,) * L
    return rdm_2q_half(state.reshape(shape)).reshape(-1, 4, 4)


def fidelity(psi, phi):
    psi = psi.ravel()
    phi = phi.ravel()
    return np.abs(np.dot(psi.conj(), phi)) ** 2


def test_get_preswap_gate(n_tests=100, verbose=False):
    """
    Test if the returned pre-swap gate in qiskit code agrees with the
    `_preswap` flag in the RL environment.
    """
    N_STEPS = 6
    env = QuantumEnv(4, 1, obs_fn="phase_norm")
    P = np.eye(4,4,dtype=np.complex64)
    P[[2,1]] = P[[1,2]]
    result = True
    failed = 0
    for _ in range(n_tests):
        env.reset()
        env.simulator.set_random_states_()
        # Rollout a trajectory
        for _ in range(N_STEPS):
            psi = env.simulator.states[0].copy()
            rdms6 = observe_rdms(psi)
            a = int(np.random.randint(0, env.simulator.num_actions))
            i, j = env.simulator.actions[a]
            ent = env.simulator.entanglements[0]
            env.step([a], reset=False)
            qiskit_swap = np.all(get_preswap_gate(rdms6, i, j) == P)
            env_swap = env.simulator.preswaps_[0]
            res = (qiskit_swap == env_swap)
            print('.' if res else 'F', end='', flush=True)
            if not res and verbose:
                print(f'\nAction: ({i}, {j})\n')
                print('\nEntanglements before action (qiskit):\n',
                      get_entanglements(psi))
                print('\nEntanglements before action (RL env):\n', ent)
                print('\nqiskit swap:', qiskit_swap)
                print('\nRL env swap:', env_swap)
                print('\n\n')
            result &= res
            failed += int(not res)
    print('\ntest_get_preswap_gate():', f'{failed}/{N_STEPS*n_tests} failed')
    return result


def test_get_postswap_gate(n_tests=100, verbose=False):
    """
    Test if the returned post-swap gate in qiskit code agrees with the
    `_postswap` flag in the RL environment.
    """
    N_STEPS = 6
    env = QuantumEnv(4, 1, obs_fn="phase_norm")
    P = np.eye(4,4,dtype=np.complex64)
    P[[1, 2]] = P[[2, 1]]
    result = True
    failed = 0

    for _ in range(n_tests):
        env.reset()
        env.simulator.set_random_states_()
        # Rollout a trajectory
        for _ in range(N_STEPS):
            psi = env.simulator.states[0].copy()
            rdms6 = observe_rdms(psi)
            a = int(np.random.randint(0, env.simulator.num_actions))
            i, j = env.simulator.actions[a]
            env.step([a], reset=False)
            qiskit_swap = np.all(get_postswap_gate(rdms6, i, j) == P)
            env_swap = env.simulator.postswaps_[0]
            res = (qiskit_swap == env_swap)
            result &= res
            failed += int(not res)
            print('.' if res else 'F', end='', flush=True)
            if not res and verbose:
                print('\nAction:\n', (i, j))
                print('\nEntanglements before U:\n', get_entanglements(psi))
                U = get_U(rdms6, i, j, apply_preswap=True, apply_postswap=True)
                _, ent, _ = peek_next_4q(psi, U, i, j)
                print('\nEntanglements after U (qiskit):\n', ent)
                print('\nEntanglements after U (RL env):\n',
                      get_entanglements(env.simulator.states[0]))
    print('\ntest_get_postwap_gate():', f'{failed}/{N_STEPS*n_tests} failed')
    return result


def test_get_U(n_tests=100, verbose=False):
    """
    Test if the returned action gate U in qiskit code equals the  `_Us`
    attribute in the RL environment.
    """
    N_STEPS = 6
    env = QuantumEnv(4, 1, obs_fn="phase_norm")
    result = True
    failed = 0

    for _ in range(n_tests):
        env.reset()
        env.simulator.set_random_states_()
        # Rollout a trajectory
        for _ in range(N_STEPS):
            psi = env.simulator.states[0].copy()
            rdms6 = observe_rdms(psi)
            a = int(np.random.randint(0, env.simulator.num_actions))
            i, j = env.simulator.actions[a]
            U = get_U(rdms6, i, j, apply_preswap=True, apply_postswap=False)
            # Since `apply_preswap` is True, the returned U is already multiplied
            # on the right with swap gate (because qubits i,j needs to be swapped).
            # The effect of this matrix multiplication is that columns 2,3
            # in U are swapped.
            P = get_preswap_gate(rdms6, i, j)
            U = P @ U @ P
            env.step([a], reset=False)
            res = np.all(np.isclose(U, env.simulator.Us_[0], atol=1e-7))
            failed += int(not res)
            print('.' if res else 'F', end='', flush=True)
            if not res and verbose:
                print('\nRL env U:\n', env.simulator.Us_[0])
                print('\nqiskit U:\n', U)
                print('\n')
        result &= res
    print('\ntest_get_U():', f'{failed}/{N_STEPS*n_tests} failed')
    return result


def test_peek_next_4q(n_tests=100, verbose=False):
    """Test if peek_next_4q() returns the same states as the environment's apply()."""
    N_STEPS = 6
    env = QuantumEnv(4, 1, obs_fn="phase_norm")
    result = True
    failed = 0

    for _ in range(n_tests):
        env.reset()
        env.simulator.set_random_states_()
        res = True
        # Rollout a trajectory
        for _ in range(N_STEPS):
            psi = env.simulator.states[0].copy()
            a = int(np.random.randint(0, env.simulator.num_actions))
            i, j = env.simulator.actions[a]
            env.step([a], reset=False)
            U = get_U(observe_rdms(psi), i, j, True, True)
            phi = env.simulator.states[0]
            ent = get_entanglements(phi)
            phi2, ent2, _ = peek_next_4q(psi, U, i, j)
            res = np.isclose(fidelity(phi, phi2), 1.0, atol=1e-2)
            res &= np.all(np.isclose(ent, ent2, atol=1e-5))
            failed += int(not res)
            print('.' if res else 'F', end='', flush=True)
        result &= res
    print('\ntest_peek_next_4q():', f'{failed}/{N_STEPS*n_tests} failed')
    return result


def test_rdms_noise(policy: Literal['universal', 'transformer'], state):
    nsteps = 5 if policy == 'universal' else 8

    result = True
    for noise in [0.0, 1e-10, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
        s = state.copy()
        for _ in range(nsteps):
            rdms = observe_rdms(s)
            noisy_rdms = rdms + \
                np.random.normal(scale=noise, size=rdms.shape) + \
                1j * np.random.normal(scale=noise, size=rdms.shape)
            noisy_rdms = noisy_rdms.astype(np.complex64)
            U, i, j = get_action_4q(noisy_rdms, policy)
            s, ent, _ = peek_next_4q(s, U, i, j)
            done = np.all(ent < 1e-3)
            # Break loop early if policy != 'universal'
            if policy != 'universal' and done:
                break
        print('.' if done else 'F', end='')
        result &= done
    return result


def do_qiskit_rollout(state, max_steps=10):
    P = np.eye(4,4, dtype=np.complex64)
    P[[1,2]] = P[[2,1]]
    s = state.ravel()
    actions, states, Us, RDMs = [], [], [], []
    entanglements = []
    preswaps, postswaps = [], []
    L = int(np.log2(state.size))
    tshape = (1,) + (2,) * L

    n = 0
    done = False
    while not done and n < max_steps:
        states.append(s.copy())
        rdms = observe_rdms(s)
        RDMs.append(rdms)
        entanglements.append(get_entanglements(s))

        U, i, j = get_action_4q(rdms, "transformer")
        preswaps.append(np.all(get_preswap_gate(rdms, i, j) == P))
        postswaps.append(np.all(get_postswap_gate(rdms, i, j) == P))
        a = get_action_index_from_ij(rdms, i, j)
        s_next, ent, _ = peek_next_4q(s, U, i, j)
        done = np.all(ent < 1e-3)
        # states in RL environemnt are phase normed
        s = phase_norm(s_next.reshape(tshape)).ravel()
        actions.append(a)
        Us.append(get_U(rdms, i, j,apply_preswap=True, apply_postswap=False))
        n += 1

    states.append(s)
    RDMs.append(observe_rdms(s))
    entanglements.append(get_entanglements(s))

    return {
        "states": np.array(states),
        "actions": np.array(actions),
        "entanglements": np.array(entanglements),
        "Us": np.array(Us),
        "RDMs": np.array(RDMs),
        "preswaps": np.array(preswaps),
        "postswaps": np.array(postswaps)
    }


def do_rlenv_rollout(state, max_steps=10):
    L = int(np.log2(state.size))
    env = QuantumEnv(L, 1, obs_fn="rdm_2q_mean_real")
    env.reset()
    env.simulator.states = state.reshape((1,) + (2,) * L)

    actions, states, Us = [], [], []
    entanglements = []
    RDMs = []
    preswaps, postswaps = [], []

    if L == 4:
        policy_net = POLICY_4Q
    elif L == 5:
        policy_net = POLICY_5Q
    elif L == 6:
        policy_net = POLICY_6Q
    else:
        raise ValueError(f"No policy available for {L} qubits.")

    done = False
    n = 0
    while not done and n < max_steps:
        s = env.simulator.states.copy()
        states.append(s.ravel())
        entanglements.append(get_entanglements(s.ravel()))
        RDMs.append(observe_rdms(s))
        a = eval_policy(env.obs_fn(s)[0], policy_net)
        _, _, done, _, _ = env.step([a], reset=False)
        actions.append(a)
        Us.append(env.simulator.Us_.copy())
        preswaps.append(env.simulator.preswaps_[0])
        postswaps.append(env.simulator.postswaps_[0])
        n += 1

    s = env.simulator.states.copy().ravel()
    states.append(s)
    RDMs.append(observe_rdms(s))
    entanglements.append(get_entanglements(s))

    return {
        "states": np.array(states),
        "actions": np.array(actions),
        "entanglements": np.array(entanglements),
        "Us": np.array(Us),
        "RDMs": np.array(RDMs),
        "preswaps": np.array(preswaps),
        "postswaps": np.array(postswaps)
    }


def test_rollout_equivalence(n_qubits=4, n_tests=200):
    env = QuantumEnv(n_qubits, 1, obs_fn="phase_norm")
    result = True
    failed = 0
    max_steps = {4: 10, 5: 30, 6: 70}[n_qubits]
    # diverging_states = []

    for _ in range(n_tests):
        env.reset()
        env.simulator.set_random_states_()
        psi = env.simulator.states.ravel().copy()
        qiskit_rollout = do_qiskit_rollout(psi.copy(), max_steps)
        rl_env_rollout = do_rlenv_rollout(psi.copy(), max_steps)
        res = True
        # Test action selection
        if len(qiskit_rollout['actions']) != len(rl_env_rollout['actions']):
            res = False
        else:
            res = np.all(qiskit_rollout['actions'] == rl_env_rollout['actions'])
        # Test states overlap / fidelity
        overlaps = []
        for x, y in zip(qiskit_rollout["states"], rl_env_rollout["states"]):
            overlaps.append(fidelity(x, y))
        overlaps = np.array(overlaps)
        res &= np.all(np.isclose(np.abs(overlaps - 1.0), 0.0, atol=1e-2))
        # if not res:
        #     diverging_states.append(psi)
        #     print()
        #     print(qiskit_rollout['entanglements'])
        #     print(rl_env_rollout['entanglements'])
        #     print(qiskit_rollout['actions'], rl_env_rollout['actions'])
        #     print(qiskit_rollout['preswaps'], rl_env_rollout['preswaps'])
        #     print(qiskit_rollout['postswaps'], rl_env_rollout['postswaps'])
        #     print(overlaps)
        #     print()
        print('.' if res else 'F', end='', flush=True)
        failed += int(not res)
        result &= res
    print(f'\ntest_rollout_equivalence(n_qubits={n_qubits}):',
          f'{failed}/{n_tests} failed')
    # np.save('diverging-states.npy', np.array(diverging_states))
    return result


if __name__ == '__main__':
    np.set_printoptions(precision=2, suppress=True)

    test_get_preswap_gate(100, verbose=True)
    test_get_postswap_gate(100, verbose=True)
    test_get_U(100, verbose=True)
    test_peek_next_4q(100)
    test_rollout_equivalence(4, 100)
    test_rollout_equivalence(5, 25)
    test_rollout_equivalence(6, 10)

    # Test |BB>|BB> and all it's permutations state wih noise added to RDMs
    print('Testing |BB>|BB> state with universal circuit:')
    bell = np.sqrt(1/2) * np.array([1.0, 0.0, 0.0, 1.0])
    psi = np.kron(bell, bell).reshape(2, 2, 2, 2)   # 01-23 entangled
    for P in itertools.permutations(range(4)):
        print(f'\n\tPermutation {P}: ', end='')
        test_rdms_noise('universal', np.transpose(psi, P))

    # Test |BB>|BB> and all it's permutations state wih noise added to RDMs
    print('\n\nTesting |BB>|BB> state with transformer policy:')
    bell = np.sqrt(1/2) * np.array([1.0, 0.0, 0.0, 1.0])
    psi = np.kron(bell, bell).reshape(2, 2, 2, 2)   # 01-23 entangled
    for P in itertools.permutations(range(4)):
        print(f'\n\tPermutation {P}: ', end='')
        test_rdms_noise('transformer', np.transpose(psi, P))
    print()
