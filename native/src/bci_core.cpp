#include <iostream>
#include <cmath>
#include <vector>
#include <numeric>

#if defined(_WIN32) || defined(_WIN64)
    #define EXPORT_API __declspec(dllexport)
#else
    #define EXPORT_API __attribute__((visibility("default")))
#endif

extern "C" {

    struct CovarianceState {
        int n;
        double alpha;
        double gamma;
        double* L;
    };

    EXPORT_API CovarianceState* create_covariance_engine(int n, double alpha, double gamma) {
        CovarianceState* state = new CovarianceState();
        state->n = n;
        state->alpha = alpha;
        state->gamma = gamma;
        state->L = new double[n * n]();
        for (int i = 0; i < n; ++i) {
            state->L[i * n + i] = 1.0;
        }
        return state;
    }

    EXPORT_API void rank1_update_cholesky(CovarianceState* state, const double* x, double weight_modifier) {
        int n = state->n;
        double effective_alpha = state->alpha * weight_modifier;
        double sqrt_one_minus_a = std::sqrt(1.0 - effective_alpha);
        double sqrt_a = std::sqrt(effective_alpha);

        std::vector<double> v(n);
        for (int i = 0; i < n; ++i) {
            v[i] = sqrt_a * x[i];
            for (int j = 0; j < n; ++j) {
                state->L[i * n + j] *= sqrt_one_minus_a;
            }
        }

        for (int i = 0; i < n; ++i) {
            double r = std::hypot(state->L[i * n + i], v[i]);
            if (r < 1e-12) continue;

            double c = state->L[i * n + i] / r;
            double s = v[i] / r;

            state->L[i * n + i] = r;

            #pragma omp simd
            for (int j = i + 1; j < n; ++j) {
                double L_ij = state->L[j * n + i];
                double v_j = v[j];
                state->L[j * n + i] = c * L_ij + s * v_j;
                v[j] = -s * L_ij + c * v_j;
            }
        }
    }

    EXPORT_API void get_shrunk_covariance(CovarianceState* state, double* out_sigma) {
        int n = state->n;

        for (int i = 0; i < n; ++i) {
            for (int j = 0; j < n; ++j) {
                double val = 0.0;
                for (int k = 0; k <= std::min(i, j); ++k) {
                    val += state->L[i * n + k] * state->L[j * n + k];
                }
                out_sigma[i * n + j] = val;
            }
        }

        double trace = 0.0;
        for (int i = 0; i < n; ++i) {
            trace += out_sigma[i * n + i];
        }
        double shrinkage_target = trace / n;

        for (int i = 0; i < n; ++i) {
            for (int j = 0; j < n; ++j) {
                if (i == j) {
                    out_sigma[i * n + j] = (1.0 - state->gamma) * out_sigma[i * n + j] + state->gamma * shrinkage_target;
                } else {
                    out_sigma[i * n + j] = (1.0 - state->gamma) * out_sigma[i * n + j];
                }
            }
        }
    }

    EXPORT_API void destroy_covariance_engine(CovarianceState* state) {
        if (state) {
            delete[] state->L;
            delete state;
        }
    }
}
