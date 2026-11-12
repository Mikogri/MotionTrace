using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Media.Playback;
namespace motion_trace_win;
public sealed partial class MainWindow
{
    private int phaseMask=15;
    private static string PhaseSettingsPath=>Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MotionTrace","chart-phases.txt");
    private void LoadPhaseFilters() {
        try {if(File.Exists(PhaseSettingsPath) && int.TryParse(File.ReadAllText(PhaseSettingsPath),out var value))phaseMask=value & 15;}catch(IOException){}catch(UnauthorizedAccessException){}
        ShowPreparation.IsChecked=(phaseMask&1)!=0;ShowLowering.IsChecked=(phaseMask&2)!=0;ShowBottomPause.IsChecked=(phaseMask&4)!=0;ShowLifting.IsChecked=(phaseMask&8)!=0;
    }
    private void OnPhaseFilterChanged(object sender,RoutedEventArgs e) {
        phaseMask=(ShowPreparation.IsChecked==true?1:0)|(ShowLowering.IsChecked==true?2:0)|(ShowBottomPause.IsChecked==true?4:0)|(ShowLifting.IsChecked==true?8:0);
        try {Directory.CreateDirectory(Path.GetDirectoryName(PhaseSettingsPath)!);File.WriteAllText(PhaseSettingsPath,phaseMask.ToString());}catch(Exception ex) when(ex is IOException or UnauthorizedAccessException){viewModel.ReportError(ex);}
        lastChartRender=null;DrawMovement();
    }
    private void UpdateTitleColors() {
        // Keep the native title bar; only its small icon is hidden.
        var background=Windows.UI.Color.FromArgb(255,32,32,32);
        AppWindow.TitleBar.BackgroundColor=AppWindow.TitleBar.InactiveBackgroundColor=background;
        AppWindow.TitleBar.ButtonBackgroundColor=AppWindow.TitleBar.ButtonInactiveBackgroundColor=background;
        AppWindow.TitleBar.ForegroundColor=AppWindow.TitleBar.ButtonForegroundColor=Microsoft.UI.Colors.White;
        AppWindow.TitleBar.InactiveForegroundColor=AppWindow.TitleBar.ButtonInactiveForegroundColor=Windows.UI.Color.FromArgb(255,160,160,160);
    }
    private bool chartSeekInFlight,chartDragging;
    private double? queuedChartSeek;
    private void QueueChartSeek(double time) {
        if(closed || mediaPlayer.Source is null || !Timeline.IsEnabled || !double.IsFinite(time))return;
        queuedChartSeek=time;
        if(!chartSeekInFlight)StartChartSeek();
    }
    private void StartChartSeek() {
        if(queuedChartSeek is not {} time)return;
        queuedChartSeek=null;
        time=Math.Clamp(time,0,mediaPlayer.PlaybackSession.NaturalDuration.TotalSeconds);
        if(Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds-time)<.001)return;
        chartSeekInFlight=true;
        mediaPlayer.PlaybackSession.Position=TimeSpan.FromSeconds(time);
    }
    private void OnChartSeekCompleted(MediaPlaybackSession sender,object args)=>DispatcherQueue.TryEnqueue(()=> {
        if(closed || !ReferenceEquals(sender,mediaPlayer.PlaybackSession))return;
        chartSeekInFlight=false;Render(force:true);
        if(queuedChartSeek is not null)StartChartSeek();
        if(!chartSeekInFlight && !chartDragging && resumeAfterChartSeek) {resumeAfterChartSeek=false;mediaPlayer.Play();}
    });
}
