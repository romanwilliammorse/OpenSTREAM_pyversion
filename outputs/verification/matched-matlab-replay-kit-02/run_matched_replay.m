function receipt = run_matched_replay(caseIndex, outputDirectory)
%RUN_MATCHED_REPLAY Run one case from an immutable, isolated replay bundle.
% First: run_matched_replay(1,fullfile(pwd,'results-sawai'))
% Then: run_matched_replay(2,fullfile(pwd,'results-twofluid'))
arguments
    caseIndex (1,1) double {mustBeInteger,mustBePositive}
    outputDirectory (1,1) string
end
kitRoot = fileparts(mfilename('fullpath'));
outputDirectory=string(char(java.io.File(char(outputDirectory)).getCanonicalPath()));
assert(~isfolder(outputDirectory)&&~isfile(outputDirectory),'MatchedReplay:Exists','Choose a NEW output directory.');
checks=jsondecode(fileread(fullfile(kitRoot,'checksums.json')));
for j=1:numel(checks)
    actual=sha256file(fullfile(kitRoot,checks(j).path));
    assert(strcmp(actual,checks(j).sha256),'MatchedReplay:Checksum','Bundle file changed: %s',checks(j).path);
end
kit=jsondecode(fileread(fullfile(kitRoot,'kit_manifest.json')));
assert(caseIndex<=numel(kit.cases));
selected=kit.cases(caseIndex);
oldPath=path; cleanupPath=onCleanup(@() path(oldPath)); %#ok<NASGU>
addpath(kitRoot); addpath(fullfile(kitRoot,'source'),'-begin');
% Fresh MATLAB is recommended: class definitions already loaded from another
% checkout cannot safely be replaced by changing path alone.
expected=fullfile(kitRoot,'source','+Solvers',['+' selected.framework],['@' selected.framework 'Solver'],[selected.framework 'Solver.m']);
resolved=which(['Solvers.' selected.framework '.' selected.framework 'Solver']);
assert(strcmpi(char(java.io.File(resolved).getCanonicalPath()),char(java.io.File(expected).getCanonicalPath())), ...
    'MatchedReplay:ShadowedSource','A different OpenSTREAM installation is on the MATLAB path.');
mkdir(outputDirectory);
receipt=struct('schema','openstream-matched-matlab-receipt-v1','complete',false, ...
    'run_id',selected.run_id,'kit_manifest_sha256',sha256file(fullfile(kitRoot,'kit_manifest.json')), ...
    'runtime',struct('matlab',version,'release',version('-release'),'computer',computer), ...
    'source_policy','Pinned copy plus logging calls only; original source tree untouched.');
cleanupTrace=onCleanup(@() matched_replay_trace('close',[])); %#ok<NASGU>
try
    receipt.runtime.python=char(py.sys.version);
    receipt.runtime.python_executable=char(py.sys.executable);
    cp=py.importlib.import_module('CoolProp.CoolProp');
    receipt.runtime.coolprop=char(cp.get_global_param_string('version'));
    receipt.runtime.coolprop_gitrevision=char(cp.get_global_param_string('gitrevision'));
    assert(strcmp(receipt.runtime.coolprop,kit.runtime.required_coolprop), ...
        'MatchedReplay:CoolPropVersion','Matched replay requires CoolProp %s; found %s.',kit.runtime.required_coolprop,receipt.runtime.coolprop);
    matched_replay_trace('open',fullfile(outputDirectory,'trace'));
    manifest=export_matched_reference(fullfile(kitRoot,'source'),fullfile(outputDirectory,'portable'), ...
        Framework=string(selected.framework),Source='run', ...
        InputRoot=fullfile(kitRoot,'cases',selected.run_id),ModelID=string(selected.model_id), ...
        OptionsID=string(selected.options_id),GeometryID=string(selected.geometry_id),BoundaryFile='boundary.inp');
    receipt.complete=manifest.complete;
    receipt.convergence=manifest.convergence;
    receipt.export_errors=manifest.errors;
catch ME
    receipt.error_identifier=ME.identifier;
    receipt.error=ME.getReport('extended','hyperlinks','off');
    matched_replay_trace('close',[]);
    writeReceipt();
    rethrow(ME);
end
matched_replay_trace('close',[]);
writeReceipt();
fprintf('Matched replay saved: %s\n',outputDirectory);
    function writeReceipt()
        entries=dir(fullfile(outputDirectory,'**','*'));
        receipt.artifacts=struct('path',{},'sha256',{});
        for k=1:numel(entries)
            if entries(k).isdir || strcmp(entries(k).name,'receipt.json'), continue; end
            filename=fullfile(entries(k).folder,entries(k).name);
            relative=extractAfter(string(filename),strlength(outputDirectory)+1);
            receipt.artifacts(end+1)=struct('path',char(replace(relative,'\','/')),'sha256',sha256file(filename));
        end
        fid=fopen(fullfile(outputDirectory,'receipt.json'),'w'); assert(fid>=0);
        c=onCleanup(@() fclose(fid)); %#ok<NASGU>
        fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));
    end
end

function result=sha256file(filename)
fid=fopen(filename,'rb'); assert(fid>=0); c=onCleanup(@() fclose(fid)); %#ok<NASGU>
digest=java.security.MessageDigest.getInstance('SHA-256');
digest.update(fread(fid,Inf,'*uint8'));
result=lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end
