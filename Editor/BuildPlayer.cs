using UnityEditor;
using UnityEditor.Build.Reporting;

public class BuildPlayer
{
    public static void BuildLinux()
    {
        BuildPlayerOptions opts = new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/MainScene.unity" },
            locationPathName = "build/BCIConsumer.x86_64",
            target = BuildTarget.StandaloneLinux64,
            options = BuildOptions.None,
        };

        BuildReport report = BuildPipeline.BuildPlayer(opts);
        BuildSummary summary = report.summary;

        if (summary.result == BuildResult.Succeeded)
        {
            UnityEngine.Debug.Log($"[BUILD] Success: {summary.totalSize} bytes");
        }
        else
        {
            UnityEngine.Debug.LogError($"[BUILD] Failed: {summary.result}");
        }
    }
}
