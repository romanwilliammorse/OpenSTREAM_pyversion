function matched_replay_trace(event, record)
% Observation only: no assignments into the solver workspace, no closures called.
% One-wall frozen cases only. Source hooks pass post-iteration state scalars.
persistent handles names outputRoot rawHandle
if strcmp(event,'open')
    assert(isempty(handles),'MatchedReplay:TraceOpen','A trace is already open.');
    outputRoot = record;
    mkdir(outputRoot);
    handles = struct(); names = struct();
    rawHandle = fopen(fullfile(outputRoot,'raw_locals.jsonl'),'w');
    assert(rawHandle>=0);
    return
elseif strcmp(event,'close')
    if ~isempty(handles)
        for key = string(fieldnames(handles)).'
            fclose(handles.(key));
        end
        fclose(rawHandle);
    end
    handles=[]; names=[]; outputRoot=[]; rawHandle=[];
    return
end
assert(~isempty(outputRoot),'MatchedReplay:TraceNotOpen','Open the trace first.');
if ~isfield(handles,event)
    handles.(event) = fopen(fullfile(outputRoot,event+"_trace.csv"),'w');
    assert(handles.(event)>=0);
    names.(event) = fieldnames(record);
    fprintf(handles.(event),'%s\n',strjoin(names.(event),','));
end
assert(isequal(names.(event),fieldnames(record)),'Trace column order changed.');
values = zeros(1,numel(names.(event)));
for j=1:numel(values)
    value = record.(names.(event){j});
    assert((isnumeric(value)||islogical(value)) && isscalar(value) && isreal(value), ...
        'MatchedReplay:TraceShape','Expected one real scalar for %s.',names.(event){j});
    values(j) = double(value);
end
fprintf(handles.(event),'%.17g',values(1));
fprintf(handles.(event),',%.17g',values(2:end));
fprintf(handles.(event),'\n');
if strcmp(event,'point')
    snapshot = struct('time_s',record.time_s,'node_zero_based',record.node_zero_based, ...
        'iteration',record.iteration,'locals',struct());
    % Read existing variables only. Exclude entire field objects, large axial arrays,
    % and input objects; never evaluate a new closure/property method here.
    variables = evalin('caller','whos');
    for j=1:numel(variables)
        var = variables(j);
        if ~ismember(var.class,{'double','single','logical','int32','int64','uint32','uint64'}) || prod(var.size)>16
            continue
        end
        value = evalin('caller',var.name);
        if ~isreal(value), continue; end
        entry = struct('shape',size(value),'values',[]);
        if any(~isfinite(value(:)))
            cells = num2cell(value(:));
            for k=1:numel(cells)
                if isnan(cells{k}), cells{k}='NaN';
                elseif cells{k}==Inf, cells{k}='Inf';
                elseif cells{k}==-Inf, cells{k}='-Inf'; end
            end
            entry.values = cells;
        else
            entry.values = value(:);
        end
        snapshot.locals.(var.name) = entry;
    end
    fprintf(rawHandle,'%s\n',jsonencode(snapshot));
end
end
