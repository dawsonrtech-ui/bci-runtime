using UnityEditor;
using UnityEditor.Build.Reporting;
using System.IO;

public class BuildPlayer
{
    [MenuItem("BCI Build/Topography")]
    public static void BuildTopography()
    {
        Build("build/BCITopography.exe", "Assets/Scenes/ScalpTopography.unity");
    }

    [MenuItem("BCI Build/Dashboard")]
    public static void BuildDashboard()
    {
        Build("build/BCIDashboard.exe", "Assets/Scenes/BCIDashboard.unity");
    }

    [MenuItem("BCI Build/Bar Visualiser")]
    public static void BuildBars()
    {
        Build("build/BCIBars.exe", "Assets/Scenes/SHMDemo.unity");
    }

    static void Build(string exePath, string scenePath)
    {
        if (EditorApplication.isPlaying) { UnityEngine.Debug.LogWarning("Stop Play mode first"); return; }
        string scene = File.Exists(scenePath) ? scenePath
                     : File.Exists("Assets/Scenes/ScalpTopography.unity") ? "Assets/Scenes/ScalpTopography.unity"
                     : UnityEngine.SceneManagement.SceneManager.GetActiveScene().path;
        var opts = new BuildPlayerOptions
        {
            scenes = new[] { scene },
            locationPathName = exePath,
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None,
        };
        BuildReport report = BuildPipeline.BuildPlayer(opts);
        if (report.summary.result == BuildResult.Succeeded)
            UnityEngine.Debug.Log($"[BUILD] {exePath} ({report.summary.totalSize} bytes)");
        else
            UnityEngine.Debug.LogError($"[BUILD] Failed: {report.summary.result}");
    }
}
