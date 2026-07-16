Shader "BCI/ScalpTopography"
{
    Properties
    {
        _BaseColor ("Base Color", Color) = (0.2, 0.2, 0.2, 1.0)
        _ColdColor ("Negative Charge Color", Color) = (0.0, 0.3, 1.0, 1.0)
        _HotColor ("Positive Charge Color", Color) = (1.0, 0.1, 0.0, 1.0)
        _InfluenceRadius ("Influence Radius", Float) = 0.15
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS   : POSITION;
            };

            struct Varyings
            {
                float4 positionCS   : SV_POSITION;
                float4 color        : COLOR;
            };

            uniform float3 _ElectrodePositions[16];
            uniform float _ElectrodePotentials[16];
            uniform int _ActiveChannelCount;

            float4 _BaseColor;
            float4 _ColdColor;
            float4 _HotColor;
            float _InfluenceRadius;

            Varyings vert(Attributes input)
            {
                Varyings output;
                VertexPositionInputs vertexInput = GetVertexPositionInputs(input.positionOS.xyz);
                output.positionCS = vertexInput.positionCS;

                float accumulatedPotential = 0.0;
                float totalWeight = 0.0;

                for (int i = 0; i < _ActiveChannelCount; i++)
                {
                    float dist = distance(input.positionOS.xyz, _ElectrodePositions[i]);
                    float weight = exp(-(dist * dist) / (_InfluenceRadius * _InfluenceRadius));
                    accumulatedPotential += _ElectrodePotentials[i] * weight;
                    totalWeight += weight;
                }

                float normPotential = (totalWeight > 0.0) ? (accumulatedPotential / totalWeight) : 0.0;
                normPotential = clamp(normPotential, -1.0, 1.0);

                if (normPotential >= 0.0)
                {
                    output.color = lerp(_BaseColor, _HotColor, normPotential);
                }
                else
                {
                    output.color = lerp(_BaseColor, _ColdColor, -normPotential);
                }

                return output;
            }

            float4 frag(Varyings input) : SV_Target
            {
                return input.color;
            }
            ENDHLSL
        }
    }
}
