using System.Diagnostics;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json;
using Microsoft.UI.Xaml.Media.Imaging;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Ellipse = Microsoft.UI.Xaml.Shapes.Ellipse;
using Windows.Graphics.Imaging;
using Windows.Storage;
using Windows.Media.Playback;

namespace motion_trace_win;

public sealed partial class MainWindow
{
    // Explicit local diagnostic entrypoint; normal startup never executes this workflow.
    private async Task RunComparisonSmokeAsync(string[] args)
    {
        int pointsIndex = Array.IndexOf(args, "--two-point-ui-report");
        if (pointsIndex >= 0 && pointsIndex+1 < args.Length)
        {
            if (!args.Contains("--data-directory")) throw new InvalidOperationException("Two-point smoke requires an isolated data directory.");
            string path = Path.GetFullPath(args[pointsIndex+1]);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            await Task.Delay(1000);
            mediaPlayer.Pause();
            var checks = new Dictionary<string, bool>();
            if (args.Contains("--expect-auto-points"))
                checks["automaticPointsReady"] = viewModel.TrackingPointCount == 2 && viewModel.CanAnalyze && viewModel.TrackingTimestamp == 0;
            if (args.Contains("--expect-cleared-points"))
                checks["clearSurvivesReload"] = viewModel.TrackingPointCount == 0;
            await viewModel.ClearTrackingPointsAsync();
            checks["emptyRequiresPoints"] = !viewModel.CanAnalyze && viewModel.AnalysisStateText == "Waiting for points";
            var metadata = viewModel.LoadedVideo!;
            double timestamp = mediaPlayer.PlaybackSession.Position.TotalSeconds;
            var first = new MotionTrace.Core.Athletes.Point2(metadata.Width*.3,metadata.Height*.45);
            var second = new MotionTrace.Core.Athletes.Point2(metadata.Width*.7,metadata.Height*.45);
            ZoomTrackingViewport(3);
            TrackingViewportTransform.TranslateX -= 20;
            TrackingViewportTransform.TranslateY -= 30;
            ClampTrackingPan();
            double scale = Math.Min(CorrectionCanvas.ActualWidth/metadata.Width,CorrectionCanvas.ActualHeight/metadata.Height);
            var local = new Windows.Foundation.Point((CorrectionCanvas.ActualWidth-metadata.Width*scale)/2+first.X*scale,
                (CorrectionCanvas.ActualHeight-metadata.Height*scale)/2+first.Y*scale);
            var shown = CorrectionCanvas.TransformToVisual(VideoSurface).TransformPoint(local);
            var inverted = VideoSurface.TransformToVisual(CorrectionCanvas).TransformPoint(shown);
            var recovered = VideoCoordinates.FromViewport(new(inverted.X,inverted.Y),CorrectionCanvas.ActualWidth,CorrectionCanvas.ActualHeight,metadata.Width,metadata.Height);
            checks["zoomPanOriginalCoordinates"] = recovered is {} value && Math.Abs(value.X-first.X)<.001 && Math.Abs(value.Y-first.Y)<.001;
            await viewModel.AddTrackingPointAsync(timestamp,first);
            checks["onePointCannotAnalyze"] = !viewModel.CanAnalyze && viewModel.TrackingPointCount == 1 && !Timeline.IsEnabled;
            bool mismatchRejected = false;
            try { await viewModel.AddTrackingPointAsync(timestamp+1,second); } catch (InvalidOperationException) { mismatchRejected=true; }
            checks["mixedFramesRejected"] = mismatchRejected && viewModel.TrackingPointCount == 1;
            var secondWrite = viewModel.AddTrackingPointAsync(timestamp,second);
            checks["pendingWriteBlocksAnalysis"] = secondWrite.IsCompleted || !viewModel.CanAnalyze;
            await secondWrite;
            DrawTrackingPoints();
            checks["translucentPointStyle"] = CorrectionCanvas.Children.OfType<Ellipse>().Count() == 2 &&
                CorrectionCanvas.Children.OfType<Ellipse>().All(dot =>
                dot.Fill is SolidColorBrush fill && dot.Stroke is SolidColorBrush stroke &&
                fill.Color == stroke.Color && Math.Abs(fill.Opacity-.35)<.001 && Math.Abs(stroke.Opacity-.7)<.001);
            checks["orangeAcrylicNotice"] = TrackingPointNotice.Background is AcrylicBrush acrylic &&
                Math.Abs(acrylic.Opacity-.3)<.001 && TrackingPointNotice.BorderBrush is SolidColorBrush border && border.Color.A == 153;
            checks["movementThresholdHidden"] = MotionThreshold.Visibility == Visibility.Collapsed;
            checks["twoPointsReady"] = viewModel.CanAnalyze && viewModel.AnalysisStateText == "Ready to analyze" && TrackingPointNotice.Visibility == Microsoft.UI.Xaml.Visibility.Collapsed;
            await viewModel.SelectBarbellModelAsync(0);
            checks["otherTrackersDisabled"] = viewModel.SelectedBarbellModelIndex == 2 && BarbellModelSelector.Visibility != Microsoft.UI.Xaml.Visibility.Visible ||
                viewModel.SelectedBarbellModelIndex == 2 && ((Microsoft.UI.Xaml.FrameworkElement)BarbellModelSelector.Parent).Visibility == Microsoft.UI.Xaml.Visibility.Collapsed;
            VideoSurface.Focus(FocusState.Programmatic);
            await viewModel.UndoTrackingPointAsync();
            checks["pointSaveKeepsVideoFocus"] = ReferenceEquals(FocusManager.GetFocusedElement(Root.XamlRoot), VideoSurface);
            checks["undoPreservesFirst"] = viewModel.TrackingPointCount == 1 && viewModel.SelectedTrackingPoints[0] == first && !viewModel.CanAnalyze;
            await viewModel.ClearTrackingPointsAsync();
            checks["clearResetsFrame"] = viewModel.TrackingPointCount == 0 && viewModel.TrackingTimestamp is null && !viewModel.CanAnalyze;
            var testRenderer = new Features.VideoAnalysis.PoseOverlayRenderer(OverlayCanvas, _ => { });
            PoseFrame TestFrame(Point2 point) => new(0, []) { Objects = [
                new("point-1", 1, null, null, 1, TrackingState.Tracked,
                    new(point, "tapnextpp", AnalysisQuality.Good, false, false, false)) { PointIndex = 0, MeasurementGroupId = "bar" }] };
            testRenderer.Draw(TestFrame(first), metadata, _ => true, showPose: false);
            double initialY = Canvas.GetTop(OverlayCanvas.Children.OfType<Ellipse>().Single());
            testRenderer.Draw(TestFrame(first with { Y = first.Y + metadata.Height*.1 }), metadata, _ => true, showPose: false);
            double changedY = Canvas.GetTop(OverlayCanvas.Children.OfType<Ellipse>().Single());
            checks["measurementOverlayFollowsFrame"] = changedY > initialY + 1;
            testRenderer.Clear();
            ZoomTrackingViewport(1);
            await CaptureComparisonSmokeAsync(path+".png");
            await File.WriteAllTextAsync(path,JsonSerializer.Serialize(new { checks, allPassed=checks.Values.All(v=>v),
                limitation="Application-level commands and rendered transform tested; no physical mouse input injected." }));
            if (args.Contains("--exit-after-smoke")) Close();
            return;
        }
        int loadingIndex = Array.IndexOf(args, "--loading-overlay-report");
        if (loadingIndex >= 0 && loadingIndex + 1 < args.Length)
        {
            string path = Path.GetFullPath(args[loadingIndex + 1]);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            AnalysisProgressPanel.Visibility = Microsoft.UI.Xaml.Visibility.Visible;
            var content = (Microsoft.UI.Xaml.Controls.StackPanel)AnalysisProgressPanel.Children[0];
            var ring = (Microsoft.UI.Xaml.Controls.ProgressRing)content.Children[0];
            ring.IsActive = true;
            ((Microsoft.UI.Xaml.Controls.TextBlock)content.Children[1]).Text = "42%";
            await Task.Delay(1000);
            await CaptureComparisonSmokeAsync(path + ".png");
            var position = content.TransformToVisual(VideoSurface).TransformPoint(new Windows.Foundation.Point());
            await File.WriteAllTextAsync(path, JsonSerializer.Serialize(new {
                videoWidth = VideoSurface.ActualWidth, videoHeight = VideoSurface.ActualHeight,
                overlayWidth = AnalysisProgressPanel.ActualWidth, overlayHeight = AnalysisProgressPanel.ActualHeight,
                centerX = position.X + content.ActualWidth / 2, centerY = position.Y + content.ActualHeight / 2,
                ringWidth = ring.ActualWidth, ringHeight = ring.ActualHeight,
                limitation = "Native video is excluded from RenderTargetBitmap; XAML overlay geometry is rendered."
            }));
            if (args.Contains("--exit-after-smoke")) Close();
            return;
        }
        int metadataIndex = Array.IndexOf(args, "--video-metadata-report");
        if (metadataIndex >= 0 && metadataIndex + 1 < args.Length)
        {
            await File.WriteAllTextAsync(Path.GetFullPath(args[metadataIndex + 1]), JsonSerializer.Serialize(new {
                video = viewModel.LoadedVideo, viewModel.HasTarget, viewModel.TargetNote, viewModel.AnalysisStateText
            }));
            if (args.Contains("--exit-after-smoke")) Close();
            return;
        }
        int targetIndex = Array.IndexOf(args, "--comparison-target");
        if (targetIndex >= 0 && targetIndex + 1 < args.Length)
            await viewModel.ImportComparisonTargetAsync(Path.GetFullPath(args[targetIndex + 1]));
        int reportIndex = Array.IndexOf(args, "--comparison-report");
        if (reportIndex < 0 || reportIndex + 1 >= args.Length) return;
        string reportPath = Path.GetFullPath(args[reportIndex + 1]);
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
        try
        {
            if (args.Contains("--analyze") && viewModel.Session?.Providers.Values.Count(p => p.Status == ProviderStatus.Ready) != 4)
                await viewModel.AnalyzeAsync();
            if (viewModel.Session?.Providers.Values.Count(p => p.Status == ProviderStatus.Ready) != 4)
                throw new InvalidOperationException("Four prepared providers are required for this UI smoke test. " + viewModel.SessionSummary);
            await Task.Delay(1000);
            mediaPlayer.Pause();
            mediaPlayer.PlaybackSession.Position = TimeSpan.FromSeconds(6);
            mediaPlayer.PlaybackSession.PlaybackRate = 1.25;
            await Task.Delay(500);
            var source = mediaPlayer.Source;
            var samples = new List<double>();
            var overlays = new List<double>();
            var checks = new List<object>();
            for (int i = 0; i < 40; i++)
            {
                double before = mediaPlayer.PlaybackSession.Position.TotalSeconds;
                var stopwatch = Stopwatch.StartNew();
                BarbellModelSelector.SelectedIndex = i % 4;
                stopwatch.Stop();
                samples.Add(stopwatch.Elapsed.TotalMilliseconds);
                stopwatch.Restart();
                Render(force: true);
                stopwatch.Stop();
                overlays.Add(stopwatch.Elapsed.TotalMilliseconds);
                checks.Add(new {
                    provider = viewModel.Session.ActiveProviderId,
                    analysisProvider = viewModel.Result?.Versions.BarbellProvider,
                    sameSnapshot = ReferenceEquals(viewModel.Result, viewModel.ActiveSnapshot?.Analysis),
                    sameMovement = movement is not null && ReferenceEquals(movement, preparedMovement?.Analysis),
                    reps = movement?.Reps.Count,
                    chartElements = MovementOverview.Children.Count,
                    activeRep = repSelection.ActiveRep,
                    chartMode = MainChartMode.SelectedIndex,
                    chartAxis = MainChartAxis.SelectedIndex,
                    sameSource = ReferenceEquals(source, mediaPlayer.Source),
                    positionDelta = mediaPlayer.PlaybackSession.Position.TotalSeconds - before,
                    rate = mediaPlayer.PlaybackSession.PlaybackRate,
                    state = mediaPlayer.PlaybackSession.PlaybackState.ToString(),
                    overlayElements = OverlayCanvas.Children.Count
                });
                await Task.Delay(20);
            }
            await CaptureComparisonSmokeAsync(reportPath + ".png");
            mediaPlayer.Play();
            await Task.Delay(300);
            double startPosition = mediaPlayer.PlaybackSession.Position.TotalSeconds;
            int renderedFrames = 0;
            var playbackWatch = Stopwatch.StartNew();
            for (int i = 0; i < 60; i++)
            {
                BarbellModelSelector.SelectedIndex = i % 4;
                Render(force: true);
                renderedFrames++;
                await Task.Delay(33);
            }
            var playback = new { startPosition, endPosition = mediaPlayer.PlaybackSession.Position.TotalSeconds,
                state = mediaPlayer.PlaybackSession.PlaybackState.ToString(), seconds = playbackWatch.Elapsed.TotalSeconds,
                renderedFrames, sameSource = ReferenceEquals(source, mediaPlayer.Source) };
            mediaPlayer.Pause();
            samples.Sort(); overlays.Sort();
            await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(new {
                schemaVersion = 1, warmSwitchMilliseconds = new { median = samples[samples.Count / 2], p95 = samples[(int)(samples.Count * .95)], maximum = samples[^1] },
                overlayMilliseconds = new { median = overlays[overlays.Count / 2], p95 = overlays[(int)(overlays.Count * .95)], maximum = overlays[^1] },
                checks, playback, limitation = "UI-thread updates and live playback measured; compositor presentation latency / visual video smoothness not instrumented."
            }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception ex)
        {
            await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(new { error = ex.ToString() }));
        }
        if (args.Contains("--exit-after-smoke")) Close();
    }

    private async Task CaptureComparisonSmokeAsync(string path)
    {
        var bitmap = new RenderTargetBitmap();
        // RenderTargetBitmap excludes the window Mica backdrop and native video surface.
        // An opaque theme-colored background makes translucent XAML cards readable in the diagnostic PNG.
        var previousBackground = Root.Background;
        byte shade = Root.ActualTheme == Microsoft.UI.Xaml.ElementTheme.Dark ? (byte)32 : (byte)243;
        Root.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, shade, shade, shade));
        try { await bitmap.RenderAsync(Root); }
        finally { Root.Background = previousBackground; }
        if (bitmap.PixelWidth > 0 && bitmap.PixelHeight > 0)
        {
            var pixels = await bitmap.GetPixelsAsync();
            var file = await StorageFile.GetFileFromPathAsync(CreateEmpty(path));
            using var stream = await file.OpenAsync(FileAccessMode.ReadWrite);
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied,
                (uint)bitmap.PixelWidth, (uint)bitmap.PixelHeight, 96, 96, pixels.ToArray());
            await encoder.FlushAsync();
        }
    }

    private static string CreateEmpty(string path) { File.WriteAllBytes(path, []); return path; }
}
