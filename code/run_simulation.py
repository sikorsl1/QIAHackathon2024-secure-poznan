from application import TTPProgram, ClientProgram, MerchantProgram, SimParams
from netsquid_netbuilder.base_configs import StackNetworkConfig

from squidasm.run.stack.run import run

import matplotlib.pyplot as plt
from multiprocessing import Pool
import math


LAMBDA_NUM = 20 # number of differet lambdas for one acceptable qber
SIM_RUNS = 50 # number of simulation runs for given lambda and qber
PRCESS_NUM = 8 # number processes spawned during computation
CFG = StackNetworkConfig.from_file("config_ideal.yaml")
# CFG = StackNetworkConfig.from_file("config_noisy.yaml")

def get_lambda(k: int) -> int:
    return 5 + k

def run_sim_given_acceptable_qber(qber: float):
    acceptable_qber = qber
    results = []
    for k in range(LAMBDA_NUM):
        lambda_param = get_lambda(k)
        print(f'Running for lambda={lambda_param}, acceptable QBER = {qber}')
        sim_params = SimParams.generate_params(lambda_param, acceptable_qber)
        # Create instances of programs to run
        TTP_program = TTPProgram(sim_params)
        Client_program = ClientProgram(sim_params)
        Merchant_program = MerchantProgram()

        # Run the simulation. Programs argument is a mapping of network node labels to programs to run on that node
        result = run(config=CFG, programs={"TTP": TTP_program, "Client": Client_program, "Merchant": Merchant_program},
                     num_times=SIM_RUNS)
        succes_num = 0
        for ttp_res in result[0]:
            if ttp_res['success']:
                succes_num += 1
        results.append(succes_num/SIM_RUNS)

    print(f'Acceptable QBER: {qber}, Results: {results}')
    return results

def analytical_solution(lambda_param, qber):
    result = 0
    for k in range(1, lambda_param+1):
        tmp_res = 0
        for j in range(math.floor(k*qber)+1):
            tmp_res += math.comb(k, j)*(1/4)**j*(3/4)**(k-j)
        result += math.comb(lambda_param, k)*(1/2)**lambda_param*tmp_res
    return result

def main():
    qbers = [0.0 + 0.5/8*k for k in range(PRCESS_NUM)]
    lambda_params = [get_lambda(k) for k in range(LAMBDA_NUM)]

    # main simulation
    with Pool(PRCESS_NUM) as p:
        results = p.map(run_sim_given_acceptable_qber, qbers)
        for i, res in enumerate(results):
            plt.plot(lambda_params, res, label=f'QBER {qbers[i]}')

    analytical_results = []
    for qber in qbers:
        res = [analytical_solution(lambda_param, qber) for lambda_param in lambda_params]
        analytical_results.append(res)
        plt.plot(lambda_params, res, label=f'QBER {qber} (analytical)')
    plt.legend(loc='upper left', bbox_to_anchor=(1,1))
    plt.subplots_adjust(right=0.8)
    plt.show()

if __name__ == '__main__':
    main()
