using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using motion_trace_win.Features.AthleteSelection;
using motion_trace_win.Features.VideoAnalysis;

namespace motion_trace_win;

public sealed partial class MainWindow
{
    private readonly IMotionTrajectoryProvider trajectoryProvider;
    private PlaybackChart? playbackChart;
    private bool resumeAfterChartSeek;
    private string? lastChartRender;
    private readonly RepSelectionState repSelection=new();
    private readonly Dictionary<int,CheckBox> repChecks=[];
    private bool updatingRepControls;
    private string SourceVideoId => viewModel.VideoPath ?? "";
    private ExerciseStatus[] movementStates=[];
    private MovementAnalysis? movement;
    private void OnChartPresentationChanged(object sender,SelectionChangedEventArgs e)=>DrawMovement();
    private void UpdateMovementPlayback()
    {
        if(PlaybackValue is null || MovementStatus is null)return;
        double time=mediaPlayer.PlaybackSession.Position.TotalSeconds;
        PlaybackValue.Text=playbackChart?.Update(SourceVideoId,time) ?? "No sample";
        int index=(int)(time*10);
        MovementStatus.Text=PlaybackSampleLookup.At(movement?.Points ?? [],time) is null?"No reliable movement sample":
            index>=0 && index<movementStates.Length?movementStates[index].ToString():"Waiting";
    }
    private CancellationTokenSource? movementOperation;
    private int movementRequest;
    private bool initializingMotion;

    private void ResetMotionSource()
    {
        if(MotionAthlete is null) return;
        initializingMotion=true;
        var preferred=viewModel.PreferredMotionAthleteId ?? viewModel.Result?.Frames.SelectMany(f=>f.GetShafts()).Where(s=>s.AthleteId!=null).GroupBy(s=>s.AthleteId).OrderByDescending(g=>g.Count()).FirstOrDefault()?.Key;
        MotionAthlete.SelectedItem=viewModel.Athletes.FirstOrDefault(a=>a.Id==preferred && viewModel.IsSelected(a.Id)) ?? viewModel.Athletes.FirstOrDefault(a=>viewModel.IsSelected(a.Id));
        SelectDetectedExercise();
        if(viewModel.Result is {} result && MotionAthlete.SelectedItem is AthleteRow selected)
            MotionWrist.SelectedIndex=trajectoryProvider.Extract(result.Frames,selected.Id,Joint.RightWrist).Count(s=>s.Confidence>=.4)>
                trajectoryProvider.Extract(result.Frames,selected.Id,Joint.LeftWrist).Count(s=>s.Confidence>=.4)?1:0;
        initializingMotion=false;
        UpdateCorrectionObjects();
        RefreshMovement();
    }
    private async void OnMotionSourceChanged(object sender, SelectionChangedEventArgs e)
    {
        if(initializingMotion || viewModel.IsSwitchingProvider)return;
        if(ReferenceEquals(sender,MotionAthlete))
        {
            if (MotionAthlete.SelectedItem is AthleteRow selectedAthlete) comparisonAthleteId = selectedAthlete.Id;
            initializingMotion=true;
            SelectDetectedExercise();
            initializingMotion=false;
            UpdateCorrectionObjects();
        }
        if (ReferenceEquals(sender, MotionExercise) && MotionAthlete.SelectedItem is AthleteRow athlete)
            await viewModel.SetExerciseAsync(athlete.Id, SelectedExercise());
        RefreshMovement();
    }
    private void SelectDetectedExercise()
    {
        if(MotionExercise is null)return;
        var detected=MotionAthlete.SelectedItem is AthleteRow row?viewModel.ExerciseForAthlete(row.Id):ExerciseType.Unknown;
        MotionExercise.SelectedIndex=detected switch {ExerciseType.BenchPress=>0,ExerciseType.Squat=>1,ExerciseType.Deadlift=>2,ExerciseType.Snatch=>3,ExerciseType.CleanAndJerk=>4,_=>-1};
    }
    private ExerciseType SelectedExercise() => MotionExercise.SelectedIndex switch
    { 0 => ExerciseType.BenchPress, 1 => ExerciseType.Squat, 2 => ExerciseType.Deadlift, 3 => ExerciseType.Snatch, 4 => ExerciseType.CleanAndJerk, _ => ExerciseType.Unknown };
    private void OnMotionThresholdChanged(NumberBox sender, NumberBoxValueChangedEventArgs e)
    {
        if (viewModel is not null && double.IsFinite(sender.Value) && sender.Value is >= .2 and <= 10)
            viewModel.AnalysisThreshold = sender.Value;
        RefreshMovement();
    }
    private void UpdateMovementAthleteSelection()
    {
        if (viewModel.Athletes.Count == 1)
        {
            var only = viewModel.Athletes[0];
            if (!viewModel.IsSelected(only.Id)) viewModel.SetSelected(only.Id, true);
            if (!ReferenceEquals(MotionAthlete.SelectedItem, only))
            {
                initializingMotion = true;
                try
                {
                    MotionAthlete.SelectedItem = only;
                    comparisonAthleteId = only.Id;
                    SelectDetectedExercise();
                }
                finally { initializingMotion = false; }
            }
        }
        var athlete = MotionAthlete.SelectedItem as AthleteRow;
        AthleteNotice.IsOpen = viewModel.Result is not null && !viewModel.IsBusy &&
            (athlete is null || !viewModel.IsSelected(athlete.Id));
        AthleteNotice.Title = viewModel.Athletes.Count == 0 ? "No athletes available" : "Athlete not selected";
        AthleteNotice.Message = viewModel.Athletes.Count == 0
            ? "No athlete is available for movement measurements in this analysis."
            : "Select an athlete below and enable them in the Athletes panel to display reps and movement phases.";
    }

    private async void RefreshMovement()
    {
        if(MotionThreshold is null || MotionWrist is null || MotionSource is null || MotionExercise is null || MotionNote is null ||
            RepTiles is null || closed) return;
        if (viewModel.IsSwitchingProvider || initializingMotion) return;
        UpdateMovementAthleteSelection();
        if (viewModel.Session is not null) { RefreshPreparedMovement(); return; }
        preparedMovement = null;
        int request=++movementRequest;
        movementOperation?.Cancel();
        movement=null; movementStates=[];
        UpdateExportState();
        repSelection.Reset([]);repChecks.Clear();RepTiles.Items.Clear();lastChartRender=null;
        DrawMovement();
        bool fromShaft=MotionSource.SelectedIndex==1;
        MotionWrist.IsEnabled=!fromShaft;
        MotionAthlete.IsEnabled=MotionAthlete.Items.Count>0;
        MotionAthlete.PlaceholderText=viewModel.Athletes.Count==0?"No athletes available":"Select athlete";
        var athlete=MotionAthlete.SelectedItem as AthleteRow;
        if(ExerciseNotice is not null)
            ExerciseNotice.IsOpen=viewModel.Result is not null && athlete is not null && viewModel.IsSelected(athlete.Id) && SelectedExercise()==ExerciseType.Unknown;
        if(viewModel.Result is not { } result || athlete is null)
        { MotionNote.Text="Analyze a video, then choose a measurement source."; return; }
        if(!viewModel.IsSelected(athlete.Id))
        { MotionNote.Text="Select an athlete to display movement measurements.";return; }
        if(SelectedExercise()==ExerciseType.Unknown)
        { MotionNote.Text="Exercise not detected. Select the exercise to calculate phases.";return; }
        if (SelectedExercise() is ExerciseType.Snatch or ExerciseType.CleanAndJerk)
        { MotionNote.Text = "Exercise recognized. Rep counts and phases for Olympic lifts are not supported; SBD rules are not applied."; return; }
        int athleteId=athlete.Id;
        double threshold=MotionThreshold.Value;
        if(!double.IsFinite(threshold) || threshold is < .2 or > 10)
        { MotionNote.Text="Enter a movement threshold between 0.2 and 10%."; return; }
        var wrist=MotionWrist.SelectedIndex==1?Joint.RightWrist:Joint.LeftWrist;
        var exercise=SelectedExercise();
        using var cancellation=new CancellationTokenSource();
        movementOperation=cancellation;
        MotionNote.Text="Finding movement phases…";
        try
        {
            var analyzed=await Task.Run(()=>
            {
                var provider=fromShaft ? MeasurementSources.Barbell(result) : trajectoryProvider;
                var candidates=MovementAnalyzer.AnalyzeTrajectory(provider.Extract(result.Frames,athleteId,wrist,cancellation.Token),exercise,result.Video.Height,threshold,cancellation.Token);
                if(fromShaft)return candidates with {MeasurementSource=MeasurementSources.BarbellLabel(result,athleteId),Note=$"{candidates.Reps.Count} complete reps. {MeasurementSources.BarbellLabel(result,athleteId)} · image-space px/s; camera movement and occlusion affect measurements."};
                return exercise==ExerciseType.BenchPress && result.Versions.BarbellModelVersion!="unavailable"
                    ? ShaftRepGate.Apply(candidates,result.Frames,athleteId,result.Video.Height,cancellation.Token):candidates;
            },cancellation.Token);
            if(closed || request!=movementRequest) return;
            movement=analyzed;
            UpdateExportState();
            movementStates=await Task.Run(()=>MovementStatusTimeline.Build(analyzed.Points,result.Video.DurationSeconds,result.Video.Height*.003,cancellation.Token),cancellation.Token);
            if(closed || request!=movementRequest)return;
            MotionNote.Text=$"{(fromShaft?"Barbell":athlete?.DisplayName)} · {analyzed.Note}";
            MeasurementCaption.Text=$"{analyzed.MeasurementSource} estimate · px / px/s · verify against the video";
            repSelection.Reset(analyzed.Reps.Select(r=>r.Number));
            if(analyzed.Reps.Count>0) { repSelection.Activate(analyzed.Reps[0].Number); repSelection.SelectAll(); }
            MainChartAxis.SelectedIndex=0;
            BuildRepTiles();lastChartRender=null;
            DrawMovement();
        }
        catch(OperationCanceledException) { }
        catch(Exception ex) { if(!closed && request==movementRequest) viewModel.ReportError(ex); }
        finally { if(ReferenceEquals(movementOperation,cancellation)) movementOperation=null; }
    }
    private void BuildRepTiles()
    {
        RepTiles.Items.Clear();repChecks.Clear();
        foreach(var rep in movement?.Reps ?? []) {
            var check=new CheckBox{Content=$"Rep {rep.Number} · {rep.Duration:0.00} s",IsChecked=repSelection.Selected.Contains(rep.Number)};
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(check,$"Show rep {rep.Number}");
            check.Click+=(_,_)=>{
                if(updatingRepControls)return;
                repSelection.Toggle(rep.Number);
                SyncRepSelection();
            };
            repChecks[rep.Number]=check;RepTiles.Items.Add(check);

        }
    }
    private void SyncRepSelection()
    {
        updatingRepControls=true;
        foreach(var pair in repChecks)pair.Value.IsChecked=repSelection.Selected.Contains(pair.Key);
        updatingRepControls=false;DrawMovement();
    }
    private void OnSelectAllReps(object sender,RoutedEventArgs e) {repSelection.SelectAll();SyncRepSelection();}
    private void OnClearReps(object sender,RoutedEventArgs e) {repSelection.Clear();SyncRepSelection();}
    private void SeekRep(MovementRep rep)
    {
        if(!Timeline.IsEnabled)return;
        mediaPlayer.Pause();QueueChartSeek(rep.Start);
    }
    private void OnMotionChartSizeChanged(object sender,SizeChangedEventArgs e)=>DrawMovement();
    private void OnReviewRep(object sender,RoutedEventArgs e)
    {
        if (comparedVideos.Count > 0)
        {
            if (CurrentComparedVideo?.Rep is MovementRep comparisonRep) SeekRep(comparisonRep);
            return;
        }
        if(movement?.Reps.FirstOrDefault(r=>r.Number==repSelection.ActiveRep) is { } rep)SeekRep(rep);
    }
    private void LayoutMotionCharts(bool portrait)
    {
        if(MovementOverview is null)return;
        MovementOverview.Height=portrait?Math.Clamp(Workspace.ActualHeight-500,170,300):200;
        VelocityCard.MaxHeight=portrait?double.PositiveInfinity:370;
    }
    private void DrawMovement()
    {
        if(MovementOverview is null || RepTiming is null || ReviewRepButton is null || ChartContext is null)return;
        UpdateVideoComparisonControls();
        string layout=$"{movementRequest}:{string.Join(',',repSelection.Selected.Order())}:{repSelection.ActiveRep}:{MainChartMode?.SelectedIndex}:{MainChartAxis?.SelectedIndex}:{phaseMask}:{MovementOverview.ActualWidth:0.0}:{MovementOverview.ActualHeight:0.0}:{SourceVideoId}:{comparedVideos.Count}:{string.Join(',', comparedVideos.Select(v => v.RepNumber))}:{NormalizeVideoComparison?.IsChecked}:{viewModel.IsBusy}:{viewModel.NeedsReanalysis}";
        if(lastChartRender==layout){UpdateMovementPlayback();return;}lastChartRender=layout;
        var chosen=movement?.Reps.Where(r=>repSelection.Selected.Contains(r.Number)).ToArray() ?? [];
        var axis=MainChartAxis?.SelectedIndex==1?MotionChartAxis.Rom:MotionChartAxis.Time;
        var metric=MainChartMode?.SelectedIndex==1?MotionChartMetric.Height:MotionChartMetric.Velocity;
        EnsurePlaybackChart();
        if (comparedVideos.Count > 0)
        {
            DrawVideoComparison(metric, axis);
            return;
        }
        playbackChart!.ActiveSourceVideoId = SourceVideoId;
        playbackChart.ValueUnit = null;
        IReadOnlyList<MotionChartSeries> series = viewModel.Session is not null
            ? preparedMovement?.Charts.FirstOrDefault(c => c.Metric == metric && c.Axis == axis)?.Series
                .Where(s => s.RepId == "trajectory" || int.TryParse(s.RepId, out var number) && repSelection.Selected.Contains(number)).ToArray() ?? []
            : movement is null ? [] : RepChartData.Create(SourceVideoId,movement,repSelection.Selected,metric,axis);
        series=series.Select(s=>s with {VisiblePhases=phaseMask}).ToArray();
        if(ChartHelp is not null)ChartHelp.Text=(axis==MotionChartAxis.Time?"X: seconds from preparation start. Hidden phases leave gaps; time is not compressed.":"X: lifting range of motion (ROM). 0% = bottom, 100% = top. Only lifting is displayed in this mode.")+"\n\n"+
            (metric==MotionChartMetric.Velocity?"Y: vertical velocity in pixels/second (px/s). Positive = upward movement; negative = downward movement. A falling curve means velocity is becoming more negative, not necessarily that the bar is moving down. Zero means no vertical movement.":"Y: vertical displacement in pixels (px), relative to the bottom of the lift. A rising curve means upward movement; a falling curve means downward movement.")+"\n\n"+
            $"Source: {movement?.MeasurementSource ?? "Barbell"}. These are image units, not metres or m/s. Camera movement and tracking errors can affect values.\n\n"+
            (chosen.Length>1?"Each rep has its own color, matching its table column.":"Purple: preparation. Orange: lowering. Gray: pause (bottom for bench/squat, top for deadlift). Blue: lifting.")+" Dashed vertical lines mark phase boundaries. Phase filters hide samples without changing measured durations. Drag the solid cursor to seek the active rep.";
        playbackChart.ActiveRepId=repSelection.ActiveRep?.ToString();
        playbackChart.SetSeries(series);
        ShowBottomPause.Content=MotionExercise.SelectedIndex==2?"Top pause":"Bottom pause";
        RepPicker.Content=chosen.Length==0?"Select reps":string.Join(", ",chosen.Select(r=>$"Rep {r.Number}"));
        RepTiming.Children.Clear();
        var table=new Grid {ColumnSpacing=12,RowSpacing=6};
        table.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(150)});
        foreach(var rep in chosen)table.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(100)});
        for(int i=0;i<9;i++)table.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
        void Cell(string text,int row,int col,Microsoft.UI.Xaml.Media.Brush? color=null,bool header=false) {
            var panel=new StackPanel {Orientation=Orientation.Horizontal,Spacing=6,Margin=new Thickness(0,3,0,3)};
            if(color is not null)panel.Children.Add(new Microsoft.UI.Xaml.Shapes.Ellipse {Width=8,Height=8,Fill=color,VerticalAlignment=VerticalAlignment.Center});
            panel.Children.Add(new TextBlock {Text=text,FontSize=12,FontWeight=header?Microsoft.UI.Text.FontWeights.SemiBold:Microsoft.UI.Text.FontWeights.Normal});
            Grid.SetRow(panel,row);Grid.SetColumn(panel,col);table.Children.Add(panel);
        }
        Cell("Measurement",0,0,null,true);
        string[] labels=["Preparation (s)","Lowering (s)",chosen.Any(r=>r.LoweringFollowsLifting)?"Top pause (s)":"Bottom pause (s)","Lifting (s)","Lift total (s)","With preparation (s)","Max speed (px/s)","Quality"];
        Microsoft.UI.Xaml.Media.Brush?[] colors=chosen.Length==1?[PlaybackChart.PreparationColor,PlaybackChart.LoweringColor,PlaybackChart.PauseColor,PlaybackChart.ColorFor(""),null,null,null,null]:new Microsoft.UI.Xaml.Media.Brush?[8];
        for(int i=0;i<labels.Length;i++)Cell(labels[i],i+1,0,colors[i]);
        for(int col=0;col<chosen.Length;col++) {
            var rep=chosen[col];
            Cell($"Rep {rep.Number}",0,col+1,chosen.Length>1?PlaybackChart.ColorFor($"{SourceVideoId}/{rep.Number}"):null,true);
            string F(double? value)=>value is null?"—":$"{value:0.00}";
            string[] values=[F(rep.PreparationStart is null?null:rep.PreparationSeconds),F(rep.Lowering?.Duration),F(rep.Lowering is null?null:rep.PauseSeconds),F(rep.Lifting.Duration),F(rep.Duration),F(rep.Duration+rep.PreparationSeconds),$"{rep.Lifting.PeakSpeed:0.0}",rep.Quality.ToString()];
            for(int row=0;row<values.Length;row++)Cell(values[row],row+1,col+1);
        }
        if(chosen.Length>0)RepTiming.Children.Add(table);
        else RepTiming.Children.Add(new TextBlock {Text="Select reps to show the chart and measurements.",TextWrapping=TextWrapping.Wrap});
        ReviewRepButton.IsEnabled=repSelection.ActiveRep is not null;
        ReviewRepButton.Content=repSelection.ActiveRep is { } active?$"Play #{active}":"Play rep";
        ChartContext.Text=axis==MotionChartAxis.Rom?$"X: concentric ROM · bottom 0% → top 100% · {movement?.MeasurementSource ?? "Wrist"} displacement":
            "X: seconds from preparation start · full rep · upward velocity is positive";
        UpdateMovementPlayback();
    }

    private void EnsurePlaybackChart()
    {
        if (playbackChart is not null) return;
        playbackChart = new(MovementOverview);
        playbackChart.ScrubStarted += () =>
        {
            chartDragging = true;
            resumeAfterChartSeek = mediaPlayer.PlaybackSession.PlaybackState == Windows.Media.Playback.MediaPlaybackState.Playing;
            mediaPlayer.Pause();
        };
        playbackChart.SeekRequested += QueueChartSeek;
        playbackChart.ScrubEnded += () =>
        {
            chartDragging = false;
            if (!chartSeekInFlight && resumeAfterChartSeek && !closed)
            {
                resumeAfterChartSeek = false;
                mediaPlayer.Play();
            }
        };
    }
}
