from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.qubit import Qubit

from squidasm.sim.stack.program import Program, ProgramContext, ProgramMeta
from netqasm.sdk.classical_communication.message import StructuredMessage

import hashlib
import hmac
import numpy as np
import os

from dataclasses import dataclass

MERCHANT_ID = 'BiedronkaSpZoo2137'

def get_m(client_secret, merchant_identifier):
    mac = hmac.new(key=client_secret, msg=merchant_identifier, digestmod=hashlib.sha256)
    result = '1' + mac.hexdigest()
    result_bits = bin(int(result, base=16))[3:]
    return result_bits

@dataclass
class SimParams:
    lambda_par: int = 20
    acceptable_qber: float = 0.0

    @classmethod
    def generate_params(cls, lambda_par, qber):
        params = cls()
        params.lambda_par = lambda_par
        params.acceptable_qber = qber
        return params

class TTPProgram(Program):
    PEER_NAME_forth = "Client"
    PEER_NAME_back  = "Merchant"
    CLIENT_SECRETS = {'AdamMickiewicz44': b'\xde\xad\xbe\xef'}
    
    def __init__(self, params: SimParams) -> None:
        self.lambda_par = params.lambda_par
        self.epsilon = params.acceptable_qber

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            epr_sockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            max_qubits=10,
        )

    def run(self, context: ProgramContext):
        # get classical socket to peer
        csocket_forth: Socket = context.csockets[self.PEER_NAME_forth]
        csocket_back: Socket = context.csockets[self.PEER_NAME_back]
        
        epr_socket = context.epr_sockets[self.PEER_NAME_forth]
        # get connection to quantum network processing unit
        connection = context.connection
        # sorry for this --> it was 'quick workaround' for inconsistency of data types
        clientRandBits_nparray = np.random.choice([0,1],size=self.lambda_par)
        clientRandBits_list=str(clientRandBits_nparray).replace(' ', '').replace('\n', '')[1:-1]
        clientRandBases_nparray = np.random.choice([0,1],size=self.lambda_par)
        clientRandBases_list=str(clientRandBases_nparray).replace(' ', '').replace('\n', '')[1:-1]
        # end of above apology

        for i in range(self.lambda_par):

            # generete 2 random bits for local string and coding base  
            clientRandBits=clientRandBits_list[i]
            clientRandBases=clientRandBases_list[i]
            
            # Create EPR pairs
            epr = epr_socket.create_keep()[0]

            # Qubits on a local node can be obtained, but require the connection to be initialized
            stateP=Qubit(connection)
            if(clientRandBits==str(0)):
                if clientRandBases==str(0):
                    stateP.H()
            else:
                if clientRandBases==str(0):
                    stateP.X()
                    stateP.H()
                else:
                    stateP.X()

            yield from connection.flush()

            # Teleport
            stateP.cnot(epr)
            stateP.H()
            m1 = stateP.measure()
            m2 = epr.measure()
            yield from connection.flush()

            # Send the correction information
            m1, m2 = int(m1), int(m2)

            csocket_forth.send_structured(StructuredMessage("Corrections", f"{m1},{m2}"))

        transaction_msg = yield from csocket_back.recv()
        C_id, k, M = transaction_msg.split('|')
        client_secret = self.CLIENT_SECRETS[C_id]
        m = get_m(client_secret=client_secret, merchant_identifier=M.encode())[:self.lambda_par]
        auth = self.authorize(clientRandBits_list, clientRandBases_list, k, m, epsilon=self.epsilon)

        return {'success': auth}
    
    @staticmethod
    def authorize(b, B, k, m, epsilon):
        err_counter = 0
        base_counter = 0
        for i in range(len(b)):
            if m[i] == B[i]:
                base_counter += 1
                if k[i] != b[i]:
                    err_counter += 1
        if base_counter > 0:
            qber = err_counter / base_counter
        else:
            qber = 1.0
        if qber <= epsilon:
            return True
        else:
            return False


class ClientProgram(Program):
    PEER_NAME_forth = "Merchant"
    PEER_NAME_back  = "TTP"
    
    CLIENT_PUBLIC = 'AdamMickiewicz44'
    CLIENT_SECRET = b'\xde\xad\xbe\xef'
    
    def __init__(self, params: SimParams):
        self.lambda_par = params.lambda_par

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            epr_sockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            max_qubits=10,
        )

    def run(self, context: ProgramContext):
        # get classical socket to peer
        csocket_forth = context.csockets[self.PEER_NAME_forth]
        csocket_back = context.csockets[self.PEER_NAME_back]
        
        epr_socket = context.epr_sockets[self.PEER_NAME_back]
        connection = context.connection

        merchant_id = MERCHANT_ID

        m = get_m(self.CLIENT_SECRET, merchant_id.encode())[:self.lambda_par]
        key = ''

        for i in range(self.lambda_par):

            epr = epr_socket.recv_keep()[0]
            yield from connection.flush()

            # Get the corrections
            msg = yield from csocket_back.recv_structured()
            assert isinstance(msg, StructuredMessage)
            m1, m2 = msg.payload.split(",")
            if int(m2) == 1:
                epr.X()
            if int(m1) == 1:
                epr.Z()

            # measuring state from TTP
            if not int(m[i]):
                epr.H()
            res_bit = epr.measure()

            yield from connection.flush()

            key = key + str(res_bit)

        csocket_forth.send(f'{self.CLIENT_PUBLIC}|{key}')
        yield from connection.flush()

        return {}

class MerchantProgram(Program):
    PEER_NAME_forth = "TTP"
    PEER_NAME_back  = "Client"

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            epr_sockets=[self.PEER_NAME_forth,self.PEER_NAME_back],
            max_qubits=10,
        )

    def run(self, context: ProgramContext):
        # get classical socket to peer
        csocket_back: Socket = context.csockets[self.PEER_NAME_back]
        csocket_forth: Socket = context.csockets[self.PEER_NAME_forth]
        # Merchant listens for messages on his classical socket
        
        transaction_msg = yield from csocket_back.recv()
        # malicious behavious --> malicious merchant chooses M' such that MAC(C, M) = MAC(C, M')
        malicious_merchant_id = str(np.random.randn(1) + os.getpid())
        # honest_merchant_id = MERCHANT_ID
        message = transaction_msg + f'|{malicious_merchant_id}'
        csocket_forth.send(message)
        
        return {}