using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Path = System.IO.Path;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;

namespace motion_trace_win;

public sealed partial class MainWindow
{
    // Explicit diagnostic uses synthetic movements; never runs on ordinary startup.
    private async Task RunVideoComparisonSmokeAsync(string[] args)
    {
        int index = Array.IndexOf(args, "--video-compare-ui-report");
        if (index < 0 || index+1 >= args.Length) return;
        string path = Path.GetFullPath(args[index+1]);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var checks = new Dictionary<string, bool>();
        try
        {
            MovementAnalysis Fixture(double speed, double range)
            {
                var all = new List<MovementPoint>();
                var reps = new List<MovementRep>();
                for (int rep = 0; rep < 2; rep++)
                {
                    double start = rep*8;
                    var points = Enumerable.Range(0, 91).Select(i =>
                    {
                        double t = i*.05, y = t<1 ? 0 : t<2 ? range*(t-1) : t<2.5 ? range : range*(4.5-t)/2;
                        double velocity = t<1 || t>=2 && t<2.5 ? 0 : t<2 ? range/speed : -range/(2*speed);
                        return new MovementPoint(start+t*speed, y, velocity, rep);
                    }).ToArray();
                    all.AddRange(points);
                    reps.Add(new(rep+1,
                        new(start+speed, start+2*speed, points.Where(p=>p.Time>=start+speed && p.Time<=start+2*speed).ToArray(), false),
                        new(start+2.5*speed, start+4.5*speed, points.Where(p=>p.Time>=start+2.5*speed).ToArray(), true)) { PreparationStart = start });
                }
                return new(all, reps, "Synthetic UI verification") { MeasurementSource = "Test point pair" };
            }
            await Task.Delay(800);
            initializingMotion = true;
            MotionExercise.SelectedIndex = 0;
            initializingMotion = false;
            var reference = Fixture(1, 100);
            movement = Fixture(1.2, 200);
            comparedVideos.Add(new("C:\\reference-A.mp4", 0) { Analysis = reference, Exercise = ExerciseType.BenchPress });
            comparedVideos.Add(new(SourceVideoId, 1) { Analysis = movement, Exercise = ExerciseType.BenchPress });
            comparedVideos.Add(new("C:\\reference-C.mp4", 2) { Analysis = Fixture(.8, 150), Exercise = ExerciseType.BenchPress });
            repSelection.Reset([1,2]); repSelection.SelectAll();
            lastChartRender = null; DrawMovement(); Root.UpdateLayout();
            await Task.Delay(300);
            lastChartRender = null; DrawMovement();
            checks["threeRepSelectors"] = ComparisonRepRows.Children.Count == 3 && DisplayedComparisonVideo.Items.Count == 3;
            checks["threeDistinctLineColors"] = MovementOverview.Children.OfType<Polyline>().Select(l=>(l.Stroke as SolidColorBrush)?.Color).Distinct().Count()==3;
            checks["phaseSeparators"] = MovementOverview.Children.OfType<Line>().Count(l=>l.StrokeDashArray?.Count>0)>=6;
            checks["fullMetricsTable"] = RepTiming.Children.OfType<Grid>().Single().RowDefinitions.Count==18;
            checks["seekUsesCurrentVideo"] = playbackChart?.ActiveSourceVideoId==SourceVideoId;
            ((ComboBox)((StackPanel)ComparisonRepRows.Children[1]).Children[1]).SelectedIndex = 1;
            checks["independentRepSelection"] = comparedVideos[0].RepNumber==1 && comparedVideos[2].RepNumber==1 && playbackChart?.ActiveRepId=="2";
            var selected = VideoComparison.CreateSeries(SourceVideoId, movement, new HashSet<int>{2}, MotionChartMetric.Velocity, MotionChartAxis.Time, true).Single();
            double requested = selected.TimestampAtX(1, 0)!.Value;
            QueueChartSeek(requested);
            for (int wait=0;wait<30 && Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds-requested)>.05;wait++) await Task.Delay(100);
            checks["videoSeeksToComparedRepTime"] = Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds-requested)<.05;
            phaseMask = 14; lastChartRender=null; DrawMovement();
            checks["filtersKeepPhaseSeparators"] = MovementOverview.Children.OfType<Line>().Any(l=>l.StrokeDashArray?.Count>0);
            MainChartAxis.SelectedIndex = 1;
            checks["romChartDraws"] = MovementOverview.Children.OfType<Polyline>().Count()>=2;
            MainChartAxis.SelectedIndex = 0;
            phaseMask = 15; lastChartRender=null; DrawMovement();
            await CaptureComparisonSmokeAsync(path+".png");
            var metrics = RepTiming.Children.OfType<Grid>().Single();
            checks["metricValuesPresent"] = metrics.Children.OfType<TextBlock>()
                .Single(t=>Grid.GetRow(t)==2 && Grid.GetColumn(t)==2).Text.Contains(.2.ToString("+0.000;-0.000;0.000"));
            if (VelocityCard.Child is ScrollViewer scroll)
            {
                scroll.ChangeView(null, scroll.ScrollableHeight, null, true);
                await Task.Delay(200);
                await CaptureComparisonSmokeAsync(path+".table.png");
            }
            string otherPath = Path.Combine(Path.GetDirectoryName(SourceVideoId)!, "IMG_7845.mp4");
            var saved = comparedVideos.Select(v => (v.Analysis, v.RepNumber)).ToArray();
            var next = new ComparedVideo(otherPath, 3);
            comparedVideos.Add(next);
            await SwitchComparedVideoAsync(next);
            checks["switchPreservesOtherResults"] = saved.Select((v, i) => ReferenceEquals(v.Analysis, comparedVideos[i].Analysis) && v.RepNumber == comparedVideos[i].RepNumber).All(v => v);
            checks["switchUpdatesVideoAndChartSource"] = SourceVideoId == otherPath && playbackChart?.ActiveSourceVideoId == otherPath
                && ReferenceEquals(DisplayedComparisonVideo.SelectedItem, next);
            for (int wait = 0; wait < 30 && !Timeline.IsEnabled; wait++) await Task.Delay(100);
            QueueChartSeek(2);
            for (int wait = 0; wait < 30 && Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds - 2) > .05; wait++) await Task.Delay(100);
            checks["switchedVideoSeeks"] = Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds - 2) < .05;
            bool repeatedSwitches = true;
            string firstPath = Path.Combine(Path.GetDirectoryName(otherPath)!, "100kg x 5.mp4");
            for (int cycle = 0; cycle < 4; cycle++)
            {
                var retired = mediaPlayer;
                var retiredSession = retired.PlaybackSession;
                QueueChartSeek(4);
                OpenPlaybackVideo(cycle % 2 == 0 ? firstPath : otherPath);
                OnMediaOpened(retired, new object());
                OnChartSeekCompleted(retiredSession, new object());
                for (int wait = 0; wait < 100 && !Timeline.IsEnabled; wait++) await Task.Delay(100);
                repeatedSwitches &= Timeline.IsEnabled;
                QueueChartSeek(3);
                QueueChartSeek(1);
                for (int wait = 0; wait < 100 && (chartSeekInFlight || Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds - 1) > .05); wait++) await Task.Delay(100);
                repeatedSwitches &= !chartSeekInFlight && Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds - 1) < .05;
            }
            checks["repeatedSwitchDuringSeekAndBackwardSeek"] = repeatedSwitches;
            OnEndVideoComparison(this, new RoutedEventArgs());
            viewModel.Athletes.Clear();
            var singleAthlete = new Features.AthleteSelection.AthleteRow(123, "Only athlete");
            viewModel.Athletes.Add(singleAthlete);
            initializingMotion = true;
            MotionAthlete.SelectedItem = null;
            initializingMotion = false;
            UpdateMovementAthleteSelection();
            checks["singleAthleteSelectedAutomatically"] = ReferenceEquals(MotionAthlete.SelectedItem, singleAthlete);
            checks["noWarningBeforeAnalysis"] = !AthleteNotice.IsOpen;
            checks["exitRestoresSingleVideo"] = comparedVideos.Count == 0 && RepPicker.Visibility==Visibility.Visible && VideoComparisonPanel.Visibility==Visibility.Collapsed;
            await File.WriteAllTextAsync(path, JsonSerializer.Serialize(new { synthetic = true, checks }, new JsonSerializerOptions { WriteIndented=true }));
        }
        catch (Exception ex)
        {
            await File.WriteAllTextAsync(path, JsonSerializer.Serialize(new { error=ex.ToString(), checks }));
        }
        if (args.Contains("--exit-after-smoke")) Close();
    }
}
