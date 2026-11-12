using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using MotionTrace.Infrastructure.AI;
using Windows.Storage.Pickers;

namespace motion_trace_win;
public sealed partial class MainWindow
{
    private bool exporting;
    private void UpdateExportState() {
        if(ExportButton is not null)ExportButton.IsEnabled=!exporting && !viewModel.IsBusy && viewModel.HasSelectedParticipant;
    }
    private void OnExportPackage(object sender,RoutedEventArgs e)=>ExportSelection(true,false);
    private void OnExportSamples(object sender,RoutedEventArgs e)=>ExportSelection(false,false);
    private void OnExportReps(object sender,RoutedEventArgs e)=>ExportSelection(false,true);
    private async void ExportSelection(bool video,bool timings)
    {
        if(exporting || viewModel.IsBusy || viewModel.Result is not {} result || viewModel.VideoPath is not {} source)return;
        var ids=viewModel.Athletes.Where(a=>viewModel.IsSelected(a.Id)).Select(a=>a.Id).ToHashSet();
        ids.IntersectWith(MotionTrace.Core.Analysis.AnalysisSelection.ParticipantIds(result));
        if(ids.Count==0){viewModel.ReportError(new InvalidOperationException("Select an athlete before exporting."));return;}
        var filtered=MotionTrace.Core.Analysis.AnalysisSelection.Filter(result,ids);
        var snapshot = viewModel.ActiveSnapshot;
        string? sessionId = viewModel.Session?.SessionId;
        bool shaft=MotionSource.SelectedIndex==1,debug=false,overlay=OverlayToggle.IsOn;
        var wrist=MotionWrist.SelectedIndex==1?Joint.RightWrist:Joint.LeftWrist;
        var exercises=ids.ToDictionary(id=>id,id=>viewModel.ExerciseForAthlete(id));
        var manualExercises=ids.Where(viewModel.HasManualExercise).ToDictionary(id=>id,id=>viewModel.ExerciseForAthlete(id).ToString());
        var exerciseSources=ids.ToDictionary(id=>id,viewModel.ExerciseSource);
        double threshold=MotionThreshold.Value;
        if(!double.IsFinite(threshold) || threshold is <.2 or >10)return;
        exporting=true;UpdateExportState();
        string? temporary=null;
        try {
            var picker=new FileSavePicker {SuggestedFileName=Path.GetFileNameWithoutExtension(source)+(video?"-analyzed":"-"+(timings?"reps":"samples"))};
            picker.FileTypeChoices.Add(video?"Video and analysis package":"CSV",new List<string>{video?".zip":".csv"});
            WinRT.Interop.InitializeWithWindow.Initialize(picker,WinRT.Interop.WindowNative.GetWindowHandle(this));
            var file=await picker.PickSaveFileAsync();if(file is null || closed)return;
            if(string.Equals(Path.GetFullPath(file.Path),Path.GetFullPath(source),StringComparison.OrdinalIgnoreCase))throw new IOException("Choose a different destination from the source video.");
            ExportButton.Content="Exporting…";
            temporary=Path.Combine(Path.GetTempPath(),"MotionTrace-export-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(temporary);
            var directory=temporary;
            await Task.Run(async ()=> {
                var analyses=new Dictionary<int,MovementAnalysis>();
                foreach(int id in ids.Order()) {
                    var exercise=exercises[id];
                    if (snapshot is not null)
                    {
                        var measurement = shaft ? MovementSource.Barbell : wrist == Joint.RightWrist ? MovementSource.RightWrist : MovementSource.LeftWrist;
                        analyses[id] = snapshot.FindMovement(new(id, exercise, measurement, threshold))?.Analysis
                            ?? new([], [], "Prepared phases are unavailable for this selection.");
                        continue;
                    }
                    if(exercise is not (ExerciseType.BenchPress or ExerciseType.Squat or ExerciseType.Deadlift))
                    { analyses[id]=new([],[],"Rep phases unavailable for this exercise."); continue; }
                    IMotionTrajectoryProvider provider=shaft?MeasurementSources.Barbell(filtered):new WristTrajectoryProvider();
                    var frames=filtered.Frames.Select(f=>f with {Shafts=f.Shafts?.Where(s=>s.AthleteId==id).ToArray(),Shaft=f.Shaft?.AthleteId==id?f.Shaft:null}).ToArray();
                    var candidate=MovementAnalyzer.AnalyzeTrajectory(provider.Extract(frames,id,wrist),exercise,result.Video.Height,threshold);
                    analyses[id]=(shaft?candidate:exercise==ExerciseType.BenchPress && result.Versions.BarbellModelVersion!="unavailable"?ShaftRepGate.Apply(candidate,frames,id,result.Video.Height):candidate) with {MeasurementSource=shaft?MeasurementSources.BarbellLabel(filtered,id):wrist.ToString()};
                }
                void Csv(string path,bool reps) {
                    using var writer=new StreamWriter(path,false,new UTF8Encoding(true));bool header=true;
                    foreach(var pair in analyses) {
                        using var buffer=new StringWriter();
                        if(reps)MovementCsv.WriteReps(buffer,pair.Value);else MovementCsv.WriteSamples(buffer,pair.Value);
                        using var reader=new StringReader(buffer.ToString());string? line=reader.ReadLine();
                        if(header){writer.WriteLine("athlete_id,"+line);header=false;}
                        while((line=reader.ReadLine()) is not null)writer.WriteLine(pair.Key+","+line);
                    }
                }
                if(!video){Csv(Path.Combine(directory,"output.csv"),timings);return;}
                Csv(Path.Combine(directory,"samples.csv"),false);Csv(Path.Combine(directory,"reps.csv"),true);
                using (var points = new StreamWriter(Path.Combine(directory, "points.csv"), false, new UTF8Encoding(true)))
                    TrackingPointCsv.Write(points, filtered);
                var masks = new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
                foreach(var path in filtered.Frames.SelectMany(f=>f.Objects).Select(o=>o.MaskPath).OfType<string>().Distinct())
                {
                    if(!File.Exists(path))throw new FileNotFoundException("Analysis mask artifact is missing.",path);
                    string name="masks/"+masks.Count.ToString("D7")+Path.GetExtension(path);
                    Directory.CreateDirectory(Path.Combine(directory,"masks"));
                    File.Copy(path,Path.Combine(directory,name));masks[path]=name;
                }
                var exported=filtered with {Frames=filtered.Frames.Select(f=>f with {Objects=f.Objects.Select(o=>o with {
                    MaskPath=o.MaskPath is {} p?masks[p]:null}).ToArray()}).ToArray()};
                await using(var json=File.Create(Path.Combine(directory,"analysis.json")))await AnalysisJson.WriteAsync(json,exported);
                await File.WriteAllTextAsync(Path.Combine(directory,"settings.json"),JsonSerializer.Serialize(new {sessionId,providerId=result.Versions.BarbellProvider,selectedAthleteIds=ids,measurementSource=shaft?"Barbell":wrist.ToString(),exercises=exercises.ToDictionary(p=>p.Key,p=>p.Value.ToString()),exerciseSources,manualExercises,threshold,overlay,debug,units="seconds, pixels, pixels/second; upward velocity positive"}));
                var start=new ProcessStartInfo(PythonOptions.Load().ExecutablePath) {UseShellExecute=false,CreateNoWindow=true,RedirectStandardError=true,WorkingDirectory=Path.Combine(AppContext.BaseDirectory,"ai")};
                foreach(var arg in new[]{"-m","motiontrace_ai.export_video",source,Path.Combine(directory,"analysis.json"),Path.Combine(directory,"annotated.mp4")})start.ArgumentList.Add(arg);
                if(debug)start.ArgumentList.Add("--debug");if(!overlay)start.ArgumentList.Add("--no-overlay");
                using var process=Process.Start(start) ?? throw new IOException("Could not start video export.");
                var errorTask=process.StandardError.ReadToEndAsync();await process.WaitForExitAsync();string error=await errorTask;
                if(process.ExitCode!=0)throw new IOException("Video export failed: "+error);
            });
            string output=Path.Combine(temporary,video?"output.zip":"output.csv");
            if(video)await Task.Run(()=> {
                using var zip=ZipFile.Open(output,ZipArchiveMode.Create);
                foreach(var name in new[]{"annotated.mp4","analysis.json","settings.json","samples.csv","reps.csv","points.csv"})zip.CreateEntryFromFile(Path.Combine(directory,name),name,CompressionLevel.NoCompression);
                var maskDirectory=Path.Combine(directory,"masks");
                if(Directory.Exists(maskDirectory))foreach(var mask in Directory.EnumerateFiles(maskDirectory))
                    zip.CreateEntryFromFile(mask,"masks/"+Path.GetFileName(mask),CompressionLevel.NoCompression);
            });
            await using(var input=File.OpenRead(output))await using(var destination=File.Create(file.Path))await input.CopyToAsync(destination);
            if(!closed)await new ContentDialog {XamlRoot=Root.XamlRoot,Title="Export complete",Content=file.Path,CloseButtonText="OK"}.ShowAsync();
        }
        catch(Exception ex){if(!closed)viewModel.ReportError(ex);}
        finally {
            if(temporary is not null)try{Directory.Delete(temporary,true);}catch(IOException){}catch(UnauthorizedAccessException){}
            exporting=false;if(!closed){ExportButton.Content="Export";UpdateExportState();}
        }
    }
}
