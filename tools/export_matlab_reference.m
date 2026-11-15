function manifest = export_matlab_reference(upstreamRoot, outputDir, opts)
%EXPORT_MATLAB_REFERENCE Export OpenSTREAM numerical data without MATLAB objects.
% MIT; retains OpenSTREAM's copyright in upstream/LICENSE.
% Run in a compatible MATLAB installation, including MATLAB Online when its
% Python environment can import the upstream CoolProp requirements.
%
%   addpath('tools')
%   export_matlab_reference('upstream','reference_exports/sample')
%   export_matlab_reference('upstream','reference_exports/twofluid', ...
%       Framework='TwoFluid')
%   export_matlab_reference('upstream','reference_exports/approved-mixture', ...
%       Source='approved')
%
% Source='run' executes the unchanged official sample inputs. Source='approved'
% loads the existing regression object and exports its public numerical state.
% It NEVER overwrites upstream fixtures or an existing export directory.
% CSV files contain full-precision doubles; manifest.json records exact MATLAB
% array shapes, SI units, time/history/field paths, inputs and version metadata.
% Array rows are the first MATLAB dimension; later dimensions are flattened in
% MATLAB column-major order. NaN and Inf remain NaN/Inf in CSV, not JSON null.
% This exporter has not been executed unless a corresponding run log exists.
arguments
    upstreamRoot (1,1) string
    outputDir (1,1) string
    opts.Framework (1,1) string {mustBeMember(opts.Framework,["Mixture","TwoFluid","ThreeField","FourField"])} = "Mixture"
    opts.Source (1,1) string {mustBeMember(opts.Source,["run","approved"])} = "run"
    opts.ModelID (1,1) string = "TUTORIAL1"
    opts.OptionsID (1,1) string = "DEFAULT"
    opts.GeometryID (1,1) string = "TUTORIAL1"
    opts.BoundaryFile (1,1) string = "tutorial1.inp"
end
assert(isfolder(upstreamRoot),'OpenSTREAMExport:MissingSource','Upstream folder does not exist.');
assert(~isfolder(outputDir) && ~isfile(outputDir),'OpenSTREAMExport:Exists', ...
    'Export destination already exists. Choose a new directory.');
assert(isfolder(fullfile(upstreamRoot,'+CoolPropWrapper')), ...
    'OpenSTREAMExport:MissingSubmodule','Clone upstream with --recurse-submodules.');
upstreamRoot = string(char(java.io.File(char(upstreamRoot)).getCanonicalPath()));
outputDir = string(char(java.io.File(char(outputDir)).getCanonicalPath()));
oldPath = path; cleanupPath = onCleanup(@() path(oldPath)); %#ok<NASGU>
addpath(upstreamRoot);
mkdir(outputDir); mkdir(fullfile(outputDir,'arrays')); mkdir(fullfile(outputDir,'inputs'));
diary(fullfile(outputDir,'export.log')); cleanupDiary = onCleanup(@() diary('off')); %#ok<NASGU>
manifest = struct();
manifest.schema = 'openstream-portable-reference-v1';
manifest.exporter_status = 'Executing in MATLAB; inspect complete and errors before use';
manifest.complete = false;
manifest.exported_utc = char(datetime('now','TimeZone','UTC','Format',"yyyy-MM-dd'T'HH:mm:ss'Z'"));
manifest.source_kind = char(opts.Source);
manifest.framework = char(opts.Framework);
manifest.selection = struct('modelID',opts.ModelID,'optionsID',opts.OptionsID, ...
    'geometryID',opts.GeometryID,'boundaryFile',opts.BoundaryFile);
manifest.runtime.matlab = version;
manifest.runtime.matlab_release = version('-release');
manifest.runtime.computer = computer;
manifest.runtime.python = char(py.sys.version);
cp = py.importlib.import_module('CoolProp.CoolProp');
manifest.runtime.coolprop = char(cp.get_global_param_string('version'));
manifest.runtime.coolprop_gitrevision = char(cp.get_global_param_string('gitrevision'));
manifest.upstream.version = char(openstreamVersion());
manifest.upstream.expected_commit = 'a614c7173822a93c1e64ac28d1541cbac028cbd8';
manifest.upstream.expected_wrapper_commit = 'a7c40902ff66faf6ed668986398bb1b9faa16e13';
manifest.upstream.git_commit = gitOutput(upstreamRoot,'rev-parse HEAD');
manifest.upstream.git_status = gitOutput(upstreamRoot,'status --porcelain');
manifest.upstream.submodules = gitOutput(upstreamRoot,'submodule status --recursive');
manifest.upstream.git_verification_note = 'Unavailable or mismatched Git metadata must be resolved before claiming pinned-source equivalence.';
manifest.array_layout = 'First dimension = CSV rows; remaining dimensions flattened in column-major order; use shape to restore.';
manifest.units_note = 'SI units where identified. UNRESOLVED means unit audit required; never assume dimensionless.';
manifest.arrays = struct('path',{},'file',{},'shape',{},'units',{},'matlab_class',{},'nonfinite_count',{});
manifest.errors = struct('path',{},'message',{});
inputFiles = ["models.inp","options.inp","geom.inp",opts.BoundaryFile];
manifest.input_files = struct('name',{},'sha256',{});
for name = inputFiles
    source = fullfile(upstreamRoot,'inputs',name);
    copyfile(source,fullfile(outputDir,'inputs',name));
    manifest.input_files(end+1) = struct('name',char(name),'sha256',sha256file(source));
end
copyfile(fullfile(upstreamRoot,'LICENSE'),fullfile(outputDir,'UPSTREAM_LICENSE'));
copyfile(fullfile(upstreamRoot,'+CoolPropWrapper','LICENSE'),fullfile(outputDir,'WRAPPER_LICENSE'));
try
    if opts.Source == "run"
        mkdir(fullfile(outputDir,'matlab_session'));
        inputSet = Inputs.InputSet( ...
            modelFilePath=fullfile(upstreamRoot,'inputs','models.inp'),modelID=opts.ModelID, ...
            optionsFilePath=fullfile(upstreamRoot,'inputs','options.inp'),optionsID=opts.OptionsID, ...
            geometryFilePath=fullfile(upstreamRoot,'inputs','geom.inp'),geometryID=opts.GeometryID, ...
            bcFilePath=fullfile(upstreamRoot,'inputs',opts.BoundaryFile), ...
            sessionParentDir=fullfile(outputDir,'matlab_session'), ...
            overwriteSessionFiles=false,LOGMODE='BOTH');
        constructor = str2func("Solvers." + opts.Framework + "." + opts.Framework + "Solver");
        solver = constructor(inputSet);
        timer = tic; solver.solve(); manifest.runtime.solve_seconds = toc(timer);
    else
        assert(opts.ModelID == "TUTORIAL1" && opts.OptionsID == "DEFAULT" && ...
            opts.GeometryID == "TUTORIAL1" && opts.BoundaryFile == "tutorial1.inp", ...
            'OpenSTREAMExport:FixtureSelection','Approved fixtures only cover the original TUTORIAL1 case.');
        sourceFile = fullfile(upstreamRoot,'tests','integration','references', ...
            'TUTORIAL1-TUTORIAL1-DEFAULT','tutorial1_' + opts.Framework + 'Solver.mat');
        manifest.archive.file = char(sourceFile);
        manifest.archive.sha256 = sha256file(sourceFile);
        manifest.archive.variables = whos('-file',sourceFile);
        manifest.archive.producer_versions = 'Not established: runtime metadata describes exporter, not original producer.';
        saved = load(sourceFile,'solver');
        assert(isfield(saved,'solver') && isa(saved.solver,"Solvers." + opts.Framework + "." + opts.Framework + "Solver"), ...
            'OpenSTREAMExport:FixtureClass','Expected a reconstructable OpenSTREAM solver object.');
        solver = saved.solver;
    end
    exportSolver(solver,'solver');
    manifest.complete = true;
    manifest.exporter_status = 'Complete; inspect errors for unavailable optional derived quantities.';
    writeManifest();
catch ME
    manifest.errors(end+1) = struct('path','export','message',ME.getReport('extended','hyperlinks','off'));
    writeManifest();
    rethrow(ME);
end
fprintf('Portable reference written to %s\n',outputDir);

    function exportSolver(s, prefix)
        status = struct('state',char(string(s.STATE)),'state_code',double(s.STATE));
        manifest.convergence.(matlab.lang.makeValidName(prefix)) = status;
        if ~isfield(manifest,'convergence_records')
            manifest.convergence_records = struct('path',{},'state',{},'state_code',{});
        end
        manifest.convergence_records(end+1) = struct('path',char(prefix), ...
            'state',status.state,'state_code',status.state_code);
        for key = ["NZ","NTIME","TIME","DT","Z","DZ"]
            if isprop(s,key), writeNumeric(prefix + "." + key,s.(key)); end
        end
        exportSimpleObject(s.inputSet.model,prefix + ".inputs.model");
        exportSimpleObject(s.inputSet.options,prefix + ".inputs.options");
        exportSimpleObject(s.inputSet.geometry,prefix + ".inputs.geometry");
        sample = s.inputSet.model.CBTMULT(s.Z);
        if isscalar(sample), sample = repmat(sample,size(s.Z)); end
        writeNumeric(prefix + ".function_samples.model.CBTMULT",sample);
        for j = 1:numel(s.inputSet.bc)
            exportSimpleObject(s.inputSet.bc(j),prefix + ".inputs.bc[" + (j-1) + "]");
        end
        exportSimple(s.boundaryConditions,prefix + ".boundaryConditions");
        for j = 1:numel(s.fluid)
            exportSimpleObject(s.fluid(j),prefix + ".fluid[" + (j-1) + "]");
        end
        for fieldName = ["mixture","mixtureInit","liquid","liquidInit","vapor","vaporInit","film","filmInit","drop","dropInit"]
            if ~isprop(s,fieldName), continue; end
            states = s.(fieldName);
            for j = 1:numel(states)
                exportField(states(j),prefix + "." + fieldName + "[" + (j-1) + "]");
            end
        end
        if isprop(s,'mixSolver'), exportSolver(s.mixSolver,prefix + ".mixSolver"); end
    end

    function exportField(field, prefix)
        exportSimpleObject(field,prefix);
        % W, U, H are core upstream regression quantities: a failed evaluation
        % aborts the export rather than creating an apparently usable fixture.
        for key = ["W","U","H"]
            if isprop(field,key), value = field.(key); else, value = feval(char(key),field); end
            assert(isnumeric(value) && isreal(value) && ~isempty(value),'OpenSTREAMExport:MissingCore', ...
                'Missing core quantity %s.%s.',prefix,key);
            writeNumeric(prefix + "." + key,value);
        end
        for key = ["X","XEQ","VF","RHO","MFLUX","UP","T","VR"]
            if ~ismethod(field,key), continue; end
            try
                value = feval(char(key),field);
                if isnumeric(value), writeNumeric(prefix + "." + key,value); end
            catch ME
                manifest.errors(end+1) = struct('path',char(prefix + "." + key),'message',ME.message);
            end
        end
        for name = ["liquid","vapor","base","basefilm","wave"]
            if isprop(field,name)
                nested = field.(name);
                if ~isempty(nested), exportField(nested,prefix + "." + name); end
            end
        end
    end

    function exportSimpleObject(obj, prefix)
        values = struct();
        for cellName = properties(obj)'
            name = cellName{1};
            try
                value = obj.(name);
                if isenum(value), values.(name) = char(string(value));
                elseif isa(value,'function_handle'), values.(name) = func2str(value);
                elseif ischar(value) || isstring(value), values.(name) = value;
                elseif isnumeric(value) || islogical(value) || isstruct(value)
                    exportSimple(value,prefix + "." + name);
                end
            catch ME
                manifest.errors(end+1) = struct('path',char(prefix + "." + name),'message',ME.message);
            end
        end
        manifest.text.(matlab.lang.makeValidName(prefix)) = values;
        % Preserve exact object paths independently of MATLAB field-name
        % sanitization so Python can audit effective string/enum inputs.
        if ~isfield(manifest,'text_records')
            manifest.text_records = struct('path',{},'values',{});
        end
        manifest.text_records(end+1) = struct('path',char(prefix),'values',values);
    end

    function exportSimple(value, prefix)
        if isnumeric(value) || islogical(value)
            writeNumeric(prefix,value);
        elseif isstruct(value)
            for j = 1:numel(value)
                for key = string(fieldnames(value))'
                    child = prefix + "." + key;
                    if numel(value)>1, child = prefix + "[" + (j-1) + "]." + key; end
                    exportSimple(value(j).(key),child);
                end
            end
        end
    end

    function writeNumeric(name, value)
        if ~isreal(value), return; end
        if any(strcmp({manifest.arrays.path},char(name))), return; end
        index = numel(manifest.arrays) + 1;
        relative = sprintf('arrays/%06d.csv',index);
        fid = fopen(fullfile(outputDir,relative),'w');
        assert(fid>=0,'OpenSTREAMExport:IO','Cannot write numerical array.');
        cleanupFile = onCleanup(@() fclose(fid)); %#ok<NASGU>
        if ~isempty(value)
            matrix = reshape(double(value),size(value,1),[]);
            format = [repmat('%.17g,',1,size(matrix,2)-1),'%.17g\n'];
            fprintf(fid,format,matrix.');
        end
        manifest.arrays(index) = struct('path',char(name),'file',relative, ...
            'shape',size(value),'units',unitsFor(name),'matlab_class',class(value), ...
            'nonfinite_count',sum(~isfinite(value),'all'));
    end

    function writeManifest()
        fid = fopen(fullfile(outputDir,'manifest.json'),'w');
        assert(fid>=0,'OpenSTREAMExport:IO','Cannot write manifest.');
        cleanupFile = onCleanup(@() fclose(fid)); %#ok<NASGU>
        fprintf(fid,'%s',jsonencode(manifest,PrettyPrint=true));
    end
end

function out = gitOutput(root, command)
[status,result] = system(sprintf('git -C "%s" %s',root,command));
if status == 0, out = strtrim(result); else, out = ['UNAVAILABLE: ',strtrim(result)]; end
end

function result = sha256file(filename)
fid = fopen(filename,'rb'); assert(fid>=0); cleanupFile = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid,Inf,'*uint8');
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(bytes);
result = lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end

function unit = unitsFor(path)
parts = split(string(path),'.'); key = char(parts(end));
if contains(path,'.DP.') || contains(path,'.DPSUM.'), unit='Pa'; return; end
switch key
    case {'P','PRESSURE','PCRIT','PTRIPLE','ERRORP','SSCONVP','DP'}, unit='Pa';
    case {'H','HIN','HF','HG','HFG','HMIN','HMAX','HV','HEQ','ERRORH','SSCONVH','DH','DHV'}, unit='J/kg';
    case {'W','MFLOW','WV','WBULK','ERRORW','SSCONVW','DW','DWV'}, unit='kg/s';
    case {'U','UP','VR','UC','ERRORU','SSCONVU','ERRORUF','SSCONVUF','ERRORUD','SSCONVUD','DU'}, unit='m/s';
    case {'WL','DWL','ERRORWF','SSCONVWF'}, unit='kg/s/m';
    case {'FREQUENCY','EQFREQUENCY','CSTWAVEFREQ','DF','DFW','ERRORFW','SSCONVFW'}, unit='Hz';
    case {'RHO','RHOF','RHOG'}, unit='kg/m^3';
    case {'T','TSAT','TMIN','TMAX','DTMFB'}, unit='K';
    case {'TIME','DT','TSTEP','SSTSTEP','RELAXTB','RELAXTW','RELAXCONDT','RELAXEVAPT','NEARWALLRELAXT'}, unit='s';
    case {'Z','DZ','LENGTH','PERIM','WMESH','KLOC','INTLENGTHVCST','INTLENGTHLCST','DROPDIAM','THINFILMTHICK','THINWAVETHICK'}, unit='m';
    case {'AREA'}, unit='m^2';
    case {'POWER'}, unit='W';
    case {'HFLUX','QK','QKMAX'}, unit='W/m^2';
    case {'MFLUX'}, unit='kg/(m^2 s)';
    case {'MUF','MUG'}, unit='Pa s';
    case {'KF','KG'}, unit='W/(m K)';
    case {'CPF','CPG'}, unit='J/(kg K)';
    case {'ALPHAF','ALPHAG'}, unit='m^2/s';
    case {'SIGMA'}, unit='N/m';
    case {'G'}, unit='m/s^2';
    case {'ANGLE'}, unit='degree';
    case {'NZ','NNODES','NTIME','TIDX','N','X','XEQ','VF','SLIP','WPOWER','PRANDTLF','PRANDTLG','KLOSS','CBTMULT'}, unit='1';
    otherwise, unit='UNRESOLVED';
end
end
