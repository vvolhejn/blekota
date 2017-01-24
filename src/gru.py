import numpy as np
import compander
from gru_layer import GRULayer
from param import Param


class GRU:

    def __init__(self, h_n, layer_n=1):
        self.layer_n = layer_n
        self.x_n = 256
        self.h_n = h_n

        self.layers = [GRULayer(self.x_n, h_n, name='0')]  # first layer has different dimensions
        for i in range(self.layer_n - 1):
            self.layers.append(GRULayer(h_n, h_n, name=str(i + 1)))

        self.Wy = Param(np.random.randn(self.x_n, h_n + 1) * 0.01, name='Wy')

        self.params = [self.Wy]
        for i in range(self.layer_n):
            self.params += self.layers[i].getParams()

        print('Initialized GRU with', layer_n, 'layers and', h_n, 'hidden units per layer')

    def train(self, sound, it=100):
        seq_length = 100
        loss_report_n = 100
        batches = 11

        x = np.resize(compander.quantize(sound), (batches, sound.size // batches)).T
        n = x.shape[0]
        ln = self.layer_n
        p = 0
        losses = np.zeros(loss_report_n)

        layers = self.layers
        h_prev = {}

        for i in range(it):
            # prepare inputs (we're sweeping from left to right in steps seq_length long)
            if p + seq_length + 1 >= n or i == 0:
                # reset RNN memory
                for l in range(ln):
                    h_prev[l] = np.zeros((self.h_n, batches))

                p = 0  # go from start of data
                print('New epoch (it ', (i + 1), ')')

            inputs = np.zeros((seq_length, 256, batches))
            for j in range(seq_length):
                for k in range(batches):
                    inputs[j, x[p + j, k], k] = 1

            hs, dh = {}, {}

            for l in range(self.layer_n):
                hs[l] = layers[l].forward(inputs if (l == 0) else hs[l - 1], initial_h=h_prev[l])
                h_prev[l] = np.copy(hs[l][-1])

            dh[ln - 1] = np.zeros_like(hs[ln - 1])
            loss = 0

            for j in range(seq_length):
                y = np.dot(self.Wy.a, np.r_[hs[ln - 1][j], np.ones((1, batches))])

                if np.max(y) > 500:  # learning rate too high?
                    print('Warning: y value too large: ', np.max(y))
                    np.clip(y, None, 500, out=y)

                dy = np.exp(y) / np.sum(np.exp(y), axis=0)  # also means the probabilities
                for k in range(batches):
                    loss += -np.log(dy[x[p + 1 + j, k], k])
                    dy[x[p + 1 + j, k], k] -= 1  # different derivative at the correct answer

                self.Wy.d += np.dot(dy, np.r_[hs[ln - 1][j], np.ones((1, batches))].T)
                dh[ln - 1][j] = np.dot(self.Wy.a.T, dy)[:-1, :]

            loss /= batches  # makes checking easier

            for l in reversed(range(self.layer_n)):
                dhprev = layers[l].backward(dh[l])
                if l > 0:
                    dh[l - 1] = dhprev

            losses[i % loss_report_n] = loss
            if i % loss_report_n == (loss_report_n - 1):
                print(losses)
                print('iter:\t%d\tloss:\t%f' % (i + 1, np.mean(losses)))  # print progress

            alpha = 1e-1

            for param in self.params:
                # print(param.name)
                #print(np.sum(param.d ** 2))
                param.step(alpha)

            # self.Wy.step(alpha)

            p += seq_length  # move data pointer

    def sample(self, n, hint=np.zeros(1)):
        layers = self.layers
        h = np.zeros((self.h_n, 1))
        x = np.zeros(256)
        x[compander.quantize(hint[0])] = 0
        res = np.zeros(n)
        p = np.zeros((n, 256))

        for t in range(n):
            h = layers[0].forward(x[None, :, None], initial_h=h)[0]
            y = np.dot(self.Wy.a, np.r_[h, np.ones((1, 1))])

            p[t] = (np.exp(y) / np.sum(np.exp(y))).ravel()
            chosen = np.random.choice(range(256), p=p[t])
            x = np.zeros(256)
            # use hint output if available
            x[compander.quantize(hint[t]) if (t < hint.shape[0]) else chosen] = 1

            res[t] = chosen

        self.p = p
        return compander.unquantize(res)
