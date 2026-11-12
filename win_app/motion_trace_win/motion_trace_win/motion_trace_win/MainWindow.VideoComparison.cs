using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using motion_trace_win.Features.AthleteSelection;
using motion_trace_win.Features.VideoAnalysis;
using motion_trace_win.Features.VideoImport;
using Windows.Storage.Pickers;
namespace motion_trace_win;
public sealed partial class MainWindow
{
    private sealed class ComparedVideo(string path, int color)
    {
        public string Path { get; } = path;
        public int Color { get; } = color;
        public string Label => $"{Color + 1} · {System.IO.Path.GetFileName(Path)}";
        public MovementAnalysis? Analysis { get; set; }
        public ExerciseType Exercise { get; set; }
        public int RepNumber { get; set; } = 1;
        public int ExerciseIndex { get; set; }
        public int SourceIndex { get; set; } = 1;
        public int WristIndex { get; set; }
        public int? AthleteId { get; set; }
        public MovementRep? Rep => Analysis?.Reps.FirstOrDefault(r => r.Number == RepNumber);
    }
    private readonly List<ComparedVideo> comparedVideos = [];
    private bool updatingVideoComparison;
    private bool switchingComparedVideo;
    private ComparedVideo? CurrentComparedVideo => comparedVideos.FirstOrDefault(v => string.Equals(v.Path, SourceVideoId, StringComparison.OrdinalIgnoreCase));

    private void CaptureComparedVideo()
    {
        if (switchingComparedVideo || viewModel.IsBusy || CurrentComparedVideo is not {} entry) return;
        entry.Analysis = viewModel.NeedsReanalysis ? null : movement;
        entry.Exercise = SelectedExercise();
        entry.ExerciseIndex = MotionExercise.SelectedIndex;
        entry.SourceIndex = MotionSource.SelectedIndex;
        entry.WristIndex = MotionWrist.SelectedIndex;
        entry.AthleteId = (MotionAthlete.SelectedItem as AthleteRow)?.Id;
        if (entry.Rep is null) entry.RepNumber = entry.Analysis?.Reps.FirstOrDefault()?.Number ?? 1;
    }
    private async void OnCompareVideos(object sender, RoutedEventArgs e)
    {
        if (viewModel.IsBusy || switchingComparedVideo || viewModel.VideoPath is not {} path) return;
        try
        {
            var picker = new FileOpenPicker();
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
            foreach (var extension in VideoImportService.Extensions) picker.FileTypeFilter.Add(extension);
            var files = await picker.PickMultipleFilesAsync();
            if (files.Count == 0) return;
            if (comparedVideos.Count == 0) comparedVideos.Add(new(path, 0));
            CaptureComparedVideo();
            ComparedVideo? first = null;
            foreach (var file in files)
            {
                if (comparedVideos.Any(v => string.Equals(v.Path, file.Path, StringComparison.OrdinalIgnoreCase))) continue;
                var entry = new ComparedVideo(file.Path, comparedVideos.Max(v => v.Color) + 1);
                comparedVideos.Add(entry);
                first ??= entry;
            }
            if (first is not null) await SwitchComparedVideoAsync(first);
            lastChartRender = null; DrawMovement();
        }
        catch (Exception ex) { viewModel.ReportError(ex); }
    }
    private async Task SwitchComparedVideoAsync(ComparedVideo entry)
    {
        if (viewModel.IsBusy || switchingComparedVideo || entry == CurrentComparedVideo) return;
        CaptureComparedVideo();
        switchingComparedVideo = true;
        try
        {
            await viewModel.ImportAsync(entry.Path);
            if (CurrentComparedVideo == entry && entry.Analysis is not null)
            {
                initializingMotion = true;
                MotionExercise.SelectedIndex = entry.ExerciseIndex;
                MotionSource.SelectedIndex = entry.SourceIndex;
                MotionWrist.SelectedIndex = entry.WristIndex;
                MotionAthlete.SelectedItem = viewModel.Athletes.FirstOrDefault(a => a.Id == entry.AthleteId) ?? MotionAthlete.SelectedItem;
                initializingMotion = false;
                RefreshMovement();
            }
        }
        finally
        {
            initializingMotion = false;
            switchingComparedVideo = false;
            lastChartRender = null; DrawMovement();
        }
    }
    private async void OnDisplayedVideoChanged(object sender, SelectionChangedEventArgs e)
    {
        if (updatingVideoComparison || DisplayedComparisonVideo.SelectedItem is not ComparedVideo entry) return;
        try { await SwitchComparedVideoAsync(entry); }
        catch (Exception ex) { viewModel.ReportError(ex); }
    }
    private void OnEndVideoComparison(object sender, RoutedEventArgs e)
    {
        comparedVideos.Clear(); lastChartRender = null; DrawMovement();
    }
    private void OnVideoComparisonNormalizationChanged(object sender, RoutedEventArgs e)
    {
        lastChartRender = null; DrawMovement();
    }
    private void UpdateVideoComparisonControls()
    {
        if (CompareVideosButton is null) return;
        bool comparing = comparedVideos.Count > 0;
        CompareVideosButton.IsEnabled = !viewModel.IsBusy && !switchingComparedVideo && (comparing || !viewModel.NeedsReanalysis && movement?.Reps.Count > 0);
        CompareVideosButton.Content = comparing ? "Add videos…" : "Compare videos…";
        EndVideoComparisonButton.IsEnabled = !viewModel.IsBusy && !switchingComparedVideo;
        VideoComparisonPanel.Visibility = EndVideoComparisonButton.Visibility = comparing ? Visibility.Visible : Visibility.Collapsed;
        RepPicker.Visibility = SelectAllRepsButton.Visibility = ClearRepsButton.Visibility = comparing ? Visibility.Collapsed : Visibility.Visible;
        if (!comparing) return;
        CaptureComparedVideo();
        updatingVideoComparison = true;
        try
        {
            if (DisplayedComparisonVideo.Items.Count != comparedVideos.Count) DisplayedComparisonVideo.ItemsSource = comparedVideos.ToArray();
            DisplayedComparisonVideo.SelectedItem = CurrentComparedVideo;
            DisplayedComparisonVideo.IsEnabled = !viewModel.IsBusy && !switchingComparedVideo;
            ComparisonRepRows.Children.Clear();
            foreach (var entry in comparedVideos)
            {
                var row = new StackPanel { Spacing = 4 };
                row.Children.Add(new TextBlock { Text = entry.Label, FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = PlaybackChart.ColorFor((entry.Color + 1).ToString()) });
                var reps = new ComboBox { ItemsSource = entry.Analysis?.Reps, DisplayMemberPath = "Label", SelectedItem = entry.Rep,
                    PlaceholderText = "Analyze this video to select a rep", HorizontalAlignment = HorizontalAlignment.Stretch, IsEnabled = entry.Analysis?.Reps.Count > 0 };
                Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(reps, $"Rep for {entry.Label}");
                reps.SelectionChanged += (_, _) =>
                {
                    if (updatingVideoComparison || reps.SelectedItem is not MovementRep rep) return;
                    entry.RepNumber = rep.Number; lastChartRender = null; DrawMovement();
                };
                row.Children.Add(reps); ComparisonRepRows.Children.Add(row);
            }
        }
        finally { updatingVideoComparison = false; }
    }
    private void DrawVideoComparison(MotionChartMetric metric, MotionChartAxis axis)
    {
        if (comparedVideos.Count == 0 || playbackChart is null) return;
        bool normalized = NormalizeVideoComparison.IsChecked == true;
        var series = comparedVideos.Where(v => v.Analysis is not null && v.Rep is not null)
            .SelectMany(v => VideoComparison.CreateSeries(v.Path, v.Analysis!, new HashSet<int> { v.RepNumber }, metric, axis, normalized)
                .Select(s => s with { DisplayName = $"{v.Label} · Rep {v.RepNumber}", PaletteIndex = v.Color, VisiblePhases = phaseMask })).ToArray();
        var active = CurrentComparedVideo?.Rep;
        playbackChart.ActiveSourceVideoId = SourceVideoId;
        playbackChart.ActiveRepId = active?.Number.ToString();
        playbackChart.ValueUnit = normalized ? metric == MotionChartMetric.Velocity ? "% ROM/s" : "% ROM" : null;
        playbackChart.SetSeries(series);
        ReviewRepButton.IsEnabled = active is not null && !viewModel.IsBusy;
        ReviewRepButton.Content = active is null ? "Play rep" : $"Play #{active.Number}";
        ChartContext.Text = axis == MotionChartAxis.Time ? $"{series.Length} videos · 0 s = first movement · dashed lines = phases" : $"{series.Length} videos · lifting ROM: bottom 0% → top 100%";
        MeasurementCaption.Text = normalized ? "Y: % ROM / % ROM/s. Relative motion, not m/s." : "Y: px / px/s. Camera angle, distance and resolution affect comparison.";
        ChartHelp.Text = "Each recording has its own color and rep selection. Dashed lines mark phase boundaries. Time aligns the first movement; preparation is before zero. ROM shows lifting only. Positive velocity is upward. Normalization divides displacement and velocity by each rep's ROM. Table deltas use the first recording as reference. The cursor seeks the recording selected in Displayed video. Phase filters do not change measured durations.";
        RepTiming.Children.Clear();
        if (comparedVideos.Any(v => v.Analysis is null)) RepTiming.Children.Add(new TextBlock { Text = "Select each pending recording in Displayed video and analyze it. Completed results remain in the comparison.", TextWrapping = TextWrapping.Wrap });
        if (comparedVideos.Where(v => v.Analysis is not null).Select(v => v.Exercise).Distinct().Count() > 1) RepTiming.Children.Add(new TextBlock { Text = "Different exercises selected — phase meanings may differ.", TextWrapping = TextWrapping.Wrap });
        var table = new Grid { ColumnSpacing = 12, RowSpacing = 5 };
        table.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(120) });
        foreach (var _ in comparedVideos) table.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        void Cell(string text, int row, int column, Brush? color = null)
        {
            while (table.RowDefinitions.Count <= row) table.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var cell = new TextBlock { Text = text, FontSize = 11, Margin = new Thickness(0, 3, 0, 3),
                TextWrapping = column == 0 ? TextWrapping.Wrap : TextWrapping.NoWrap,
                FontWeight = row == 0 ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal };
            if (color is not null) cell.Foreground = color;
            Grid.SetRow(cell, row); Grid.SetColumn(cell, column); table.Children.Add(cell);
        }
        Cell("Measurement", 0, 0);
        string F(double? value, bool difference = false) => value is null ? "—" : value.Value.ToString(difference ? "+0.000;-0.000;0.000" : "0.000");
        for (int i = 0; i < comparedVideos.Count; i++)
        {
            var entry = comparedVideos[i];
            Cell($"{entry.Color + 1} · Rep {entry.Rep?.Number.ToString() ?? "—"}", 0, i + 1, PlaybackChart.ColorFor((entry.Color + 1).ToString()));
            int row = 1;
            foreach (var value in VideoComparison.Compare(comparedVideos[0].Rep, entry.Rep))
            {
                if (i == 0) Cell($"{value.Label} ({value.Unit})", row, 0);
                string delta = i == 0 ? "" : $"\nΔ {F(value.Difference, true)} ({F(value.DifferencePercent, true)}%)";
                Cell(F(value.B) + delta, row++, i + 1);
            }
            if (i == 0) Cell("Quality", row, 0);
            Cell(entry.Rep?.Quality.ToString() ?? "—", row, i + 1);
        }
        RepTiming.Children.Add(table); UpdateMovementPlayback();
    }
}
