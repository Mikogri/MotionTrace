using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using MotionTrace.Core.PoseCorrection;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;
using motion_trace_win.Features.VideoAnalysis;
using motion_trace_win.Features.VideoImport;

namespace motion_trace_win;

public partial class App : Application
{
    private Window? window;
    private ServiceProvider? services;
    public App()
    {
        UnhandledException += (_, e) => new AppLog().Write($"Unhandled UI error: {e.Exception}");
        InitializeComponent();
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var log = new AppLog();
        PythonOptions options;
        try
        {
            var arguments = Environment.GetCommandLineArgs();
            int dataIndex = Array.IndexOf(arguments, "--data-directory");
            options = PythonOptions.Load(dataIndex >= 0 && dataIndex + 1 < arguments.Length ? Path.GetFullPath(arguments[dataIndex + 1]) : null);
        }
        catch (Exception ex) when (ex is System.Text.Json.JsonException or IOException or UnauthorizedAccessException)
        { log.Write($"Settings reset: {ex}"); options = new(); }
        services = new ServiceCollection()
            .AddSingleton(log).AddSingleton(options)
            .AddSingleton<PythonPoseEngine>()
            .AddSingleton<ComparisonAnalysisEngine>()
            .AddSingleton<IPoseSmoother, LightPoseSmoother>()
            .AddSingleton(options.Correction).AddSingleton<TemporalPoseCorrector>()
            .AddSingleton<IPoseAnalysisEngine>(s => new CorrectingPoseEngine(s.GetRequiredService<PythonPoseEngine>(),s.GetRequiredService<TemporalPoseCorrector>()))
            .AddSingleton<IExerciseClassifier, BenchPressClassifier>()
            .AddSingleton<IBarbellTracker, UnavailableBarbellTracker>()
            .AddSingleton<IMotionTrajectoryProvider, WristTrajectoryProvider>()
            .AddSingleton<VideoImportService>().AddSingleton<AnalysisViewModel>()
            .AddSingleton<MainWindow>().BuildServiceProvider();
        window = services.GetRequiredService<MainWindow>();
        window.Closed += (_, _) => services.Dispose();
        window.Activate();
    }
}
