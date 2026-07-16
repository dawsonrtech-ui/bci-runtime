using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.Build;
using System;

public class BuildPlayer
{
    private static void Build(string location, BuildTarget target,
                              BuildTargetGroup group, BuildOptions opts)
    {
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/MainScene.unity" },
            locationPathName = location,
            targetGroup = group,
            target = target,
            options = opts,
        });
        var summary = report.summary;
        if (summary.result == BuildResult.Succeeded)
            UnityEngine.Debug.Log($"[BUILD] OK  {location}  ({summary.totalSize} bytes)");
        else
            UnityEngine.Debug.LogError($"[BUILD] FAILED  {location}  ({summary.result})");
    }

    public static void BuildLinuxMono()
    {
        Build("build/BCIConsumer.x86_64",
              BuildTarget.StandaloneLinux64,
              BuildTargetGroup.Standalone,
              BuildOptions.None);
    }

    public static void BuildLinuxIL2CPP()
    {
        Build("build/BCIConsumer_il2cpp.x86_64",
              BuildTarget.StandaloneLinux64,
              BuildTargetGroup.Standalone,
              BuildOptions.CompressWithLz4HC);
        // Note: scripting backend switch requires either:
        //   PlayerSettings.SetScriptingBackend(group, ScriptingImplementation.IL2CPP);
        //   or setting via project Settings before calling this method.
    }

    public static void BuildWindowsIL2CPP()
    {
        Build("build/BCIConsumer_Win.exe",
              BuildTarget.StandaloneWindows64,
              BuildTargetGroup.Standalone,
              BuildOptions.CompressWithLz4HC);
    }

    public static void BuildAll()
    {
        BuildLinuxMono();
        BuildLinuxIL2CPP();
        BuildWindowsIL2CPP();
    }
}
