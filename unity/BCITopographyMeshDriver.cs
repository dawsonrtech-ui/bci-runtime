using UnityEngine;

public class BCITopographyMeshDriver : MonoBehaviour
{
    private Material _topoMaterial;

    [Header("Electrode Spatial Mapping Setup")]
    public Transform[] electrodeTransforms;

    private Vector4[] _gpuPositions = new Vector4[16];
    private float[] _gpuPotentials = new float[16];

    private void Start()
    {
        _topoMaterial = GetComponent<MeshRenderer>().material;
        int channels = Mathf.Min(electrodeTransforms.Length, 16);
        _topoMaterial.SetInt("_ActiveChannelCount", channels);

        for (int i = 0; i < channels; i++)
        {
            Vector3 localPos = transform.InverseTransformPoint(electrodeTransforms[i].position);
            _gpuPositions[i] = new Vector4(localPos.x, localPos.y, localPos.z, 1.0f);
        }
        _topoMaterial.SetVectorArray("_ElectrodePositions", _gpuPositions);
    }

    public void UpdateScalpPotentials(float[] incomingPotentials)
    {
        int limit = Mathf.Min(incomingPotentials.Length, 16);
        for (int i = 0; i < limit; i++)
        {
            _gpuPotentials[i] = incomingPotentials[i];
        }
        _topoMaterial.SetFloatArray("_ElectrodePotentials", _gpuPotentials);
    }
}
