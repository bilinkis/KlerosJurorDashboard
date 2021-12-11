# -*- coding: utf-8 -*-
"""plotters
Functions to create the graphs for the website.
"""
import json
from datetime import datetime
import logging

import plotly.graph_objs as go
# from plotly.subplots import make_subplots
# from plotly.express import colors as colormap
from plotly.utils import PlotlyJSONEncoder
import pandas as pd

from app.modules.subgraph import KlerosBoardSubgraph

logger = logging.getLogger(__name__)

"""
def multiBar(df, columns=['0', '2', '8', '9']):
    fig = go.Figure()
    for column in df.columns.to_list():
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df[column],
                name=Court(id=int(column)).map_name,
                visible=True if column in columns else 'legendonly'
            )
        )

    fig.update_layout(barmode='stack',
                      legend={'orientation': 'h'}
                      )

    return json.dumps(fig, cls=PlotlyJSONEncoder)


def create_time_series(df, courts, colname=None):
    data = []
    colors = colormap.qualitative.Alphabet
    allCourts = df.columns.to_list()
    for i, court in enumerate(allCourts):
        if not colname:
            try:
                name = Court(id=int(court)).map_name
            except:
                # i'm trying to plot a court which not exist
                continue
        data.append(go.Bar(
                x=df.index,
                y=df[str(court)].astype(float),
                name=name,
                visible=True if str(court) in courts else 'legendonly',
                legendgroup='group'+str(court),
                marker_color=colors[i]))
    return data

"""


def disputesGraph(disputes, language="en"):
    if 'en' == language:
        ylabels = ['Disputes', 'Jurors Drawn']
        xlabel = 'Dates'
        title = 'Time Evolution of Disputes and Rounds in Kleros Courts'
    else:
        ylabels = ['Disputas', 'Jurados Seleccionados']
        xlabel = 'Fechas'
        title = 'Evolución de Disputas y Rondas en KLEROS'

    fig = go.Figure()
    df = pd.DataFrame(disputes)
    df.startTime = df.startTime.map(datetime.fromtimestamp)
    df.startTime = pd.to_datetime(df.startTime)
    df.set_index(df.startTime, inplace=True)
    df.set_index('startTime', inplace=True)
    df.sort_index(inplace=True)
    fig.add_trace(go.Scatter(x=df.index,
                             y=df['id'],
                             name=ylabels[0]))

    fig['layout'].update(height=300,
                         margin={'l': 10, 'b': 50, 't': 30, 'r': 30},
                         title=title,
                         showlegend=False)
    fig.update_yaxes(title_text="N° "+ylabels[0])
    fig.update_xaxes(title_text=xlabel)
    return json.dumps(fig, cls=PlotlyJSONEncoder)


"""
def stakesJurorsGraph(courts=['0', '2', '8', '9'], language='en'):
    if 'en' in language:
        title = 'Time evolution of Stakes in courts'
    else:
        title = 'Evolución de Depósitos por Corte'
    fig = make_subplots(rows=2, cols=1,
                        shared_xaxes=True, shared_yaxes=False,
                        vertical_spacing=0.05)

    dfStaked = pd.DataFrame()
    dfJurors = pd.DataFrame()

    t0 = time.time()
    dataEvolution = StakesEvolution.getEvolution()
    logger.debug(f"StakesEvolution.getEvolution takes {time.time()-t0} secs")
    t0 = time.time()
    for courtID in range(Court().ncourts):
        if courtID in dataEvolution.keys():
            courtdf = pd.DataFrame(dataEvolution[courtID])
            courtdf.timestamp = pd.to_datetime(courtdf.timestamp)
            dfStaked = pd.concat([dfStaked,
                                  courtdf[['timestamp', 'staked']]
                                  .set_index('timestamp').rename(
                                    columns={'staked': str(courtID)}
                                    )
                                  ],
                                 axis=1,
                                 ignore_index=False)
            dfJurors = pd.concat([dfJurors,
                                  courtdf[['timestamp',
                                           'jurors']].set_index('timestamp').rename(
                                               columns={'jurors': str(courtID)}
                                               )
                                  ],
                                 axis=1,
                                 ignore_index=False)
    logger.debug(f"Build the dataframes takes {time.time()-t0} seconds")
    traces = create_time_series(dfStaked, courts)
    for trace in traces:
        fig.append_trace(trace, row=1, col=1)

    # for courtID in range(0,Court().ncourts):
    #     jurors = pd.DataFrame(StakesEvolution.getEvolutionByCourt(
    #               int(courtID)))[['jurors','timestamp']]
    #     jurors.columns = [str(courtID), 'timestamp']
    #     jurors.timestamp = pd.to_datetime(jurors.timestamp)
    #     jurors.set_index('timestamp', inplace=True)
    #     dfJurors = pd.concat([dfJurors, jurors], axis=1)
    traces = create_time_series(dfJurors, courts)
    for trace in traces:
        trace['showlegend'] = False
        fig.append_trace(trace, row=2, col=1)
    fig['layout'].update(height=500,
                         margin={'l': 10, 'b': 50, 't': 30, 'r': 30},
                         title=title,
                         barmode='stack',
                         legend={'orientation': 'h'})
    if 'en' in language:
        fig.update_yaxes(title_text="PNK Staked", row=1, col=1)
        fig.update_yaxes(title_text="N° of Active Jurors", row=2, col=1)
        fig.update_xaxes(title_text="Date", row=2, col=1)
    else:
        fig.update_yaxes(title_text="PNK Depositados", row=1, col=1)
        fig.update_yaxes(title_text="N° de Jurados Activos", row=2, col=1)
        fig.update_xaxes(title_text="Fecha", row=2, col=1)
    return json.dumps(fig, cls=PlotlyJSONEncoder)
"""


def disputesbyCourtGraph(disputes, network=None, language="en"):
    if 'en' == language:
        title = 'Disputes by Courts'
    else:
        title = 'Disputas por Cortes'
    fig = go.Figure()
    df = pd.DataFrame(disputes)
    data = df.groupby(df.subcourtID)['id'].count()
    data.index = data.index.map(KlerosBoardSubgraph(network).getCourtName)
    data = data.to_dict()
    fig.add_trace(go.Pie(labels=list(data.keys()),
                         values=list(data.values()),
                         showlegend=False)
                  )

    fig['layout'].update(title=title,
                         height=300,
                         margin={'l': 10, 'b': 80, 't': 30, 'r': 30},
                         legend={'orientation': 'h'})
    # fig.update_yaxes(title_text='N°')
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def disputesbyArbitratedGraph(disputes, network=None, language="en"):
    if 'en' == language:
        title = 'Disputes by dApp'
    else:
        title = 'Disputas por dApp'
    fig = go.Figure()
    df = pd.DataFrame(disputes)
    df.arbitrable = df.arbitrable.map(KlerosBoardSubgraph(network).getArbitrableName)
    data = df.groupby(df.arbitrable)['id'].count()
    data = data.to_dict()
    fig.add_trace(go.Pie(labels=list(data.keys()),
                         values=list(data.values()),
                         showlegend=False)
                  )

    fig['layout'].update(title=title,
                         height=300,
                         margin={'l': 10, 'b': 80, 't': 30, 'r': 30},
                         legend={'orientation': 'h'})
    # fig.update_yaxes(title_text='N°')
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def treeMapGraph(courtTable, key="Jurors"):
    labels = [court['name'] for court in courtTable.values()]
    ids = courtTable.keys()
    parents_id = [courtTable[courtID]['parent'] for courtID in ids]
    parents = [courtTable[courtID]['name'] if courtID is not None else ""
               for courtID in parents_id]

    values = [courtTable[court_name][key] for court_name in ids]
    fig = go.Figure(
        go.Treemap(
            # ids=labels,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            hovertemplate='<b>%{label}</b>'
                          '<br>' + key + ': %{value}'
                          '<br>Percentage of Parent Court: '
                          '%{percentParent:.2%}<br>Percentage of General '
                          'Court: %{percentRoot:.2%}<br>'
        )
    )
    fig['layout'].update(height=300,
                         margin={'l': 10, 'b': 80, 't': 30, 'r': 30},
                         legend={'orientation': 'h'})
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def jurorHistogram(jurorStakes):
    fig = go.Figure(data=[go.Histogram(x=jurorStakes,
                                       nbinsx=50)])
    fig['layout'].update(height=300,
                         margin={'l': 10, 'b': 80, 't': 30, 'r': 30})
    fig.update_yaxes(title_text='N° of Jurors')
    fig.update_xaxes(title_text='PNK Staked')
    return json.dumps(fig, cls=PlotlyJSONEncoder)
