Shader "BCI/ScalpTopography"
{
    Properties
    {
        _BaseColor ("Base Color", Color) = (0.2, 0.2, 0.2, 1.0)
        _ColdColor ("Negative Charge Color", Color) = (0.0, 0.3, 1.0, 1.0)
        _HotColor ("Positive Charge Color", Color) = (1.0, 0.1, 0.0, 1.0)
        _InfluenceRadius ("Influence Radius", Float) = 0.3
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
            };

            struct v2f
            {
                float4 vertex : SV_POSITION;
                float4 color : COLOR;
            };

            uniform float3 _ElectrodePositions[16];
            uniform float _ElectrodePotentials[16];
            uniform int _ActiveChannelCount;

            float4 _BaseColor;
            float4 _ColdColor;
            float4 _HotColor;
            float _InfluenceRadius;

            v2f vert(appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                float3 worldPos = mul(unity_ObjectToWorld, v.vertex).xyz;

                float accumulatedPotential = 0.0;
                float totalWeight = 0.0;

                for (int i = 0; i < _ActiveChannelCount; i++)
                {
                    float3 ep = mul(unity_ObjectToWorld, float4(_ElectrodePositions[i], 1.0)).xyz;
                    float dist = distance(worldPos, ep);
                    float weight = exp(-(dist * dist) / (_InfluenceRadius * _InfluenceRadius));
                    accumulatedPotential += _ElectrodePotentials[i] * weight;
                    totalWeight += weight;
                }

                float normPotential = (totalWeight > 0.0) ? (accumulatedPotential / totalWeight) : 0.0;
                normPotential = clamp(normPotential, 0.0, 1.0);
                o.color = lerp(_BaseColor, _HotColor, normPotential);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                return i.color;
            }
            ENDCG
        }
    }
}
