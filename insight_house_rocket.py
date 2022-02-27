import pandas as pd
import streamlit as st
import numpy as np
from streamlit_folium import folium_static
import folium
from folium.plugins import MarkerCluster
import geopandas
import plotly.express as px


# layout da pagina
st.set_page_config( layout='wide' )

pd.set_option('display.float_format', lambda x: '%.2f' % x)

# data carregado no cache
@st.cache( allow_output_mutation=True)
def get_data( path ):
    data = pd.read_csv( path )

    return data

# leitura do geopandas
@st.cache(allow_output_mutation=True)
def get_geofile(url):
     geofile = geopandas.read_file(url)

     return geofile

#=======================================
    # limpeza de dados
def clean_data( data ):
    # date em formato de data
    data['date'] = pd.to_datetime(data['date'])
    # Converte do tipo float64 para int
    data['bathrooms'] = data['bathrooms'].astype(int)
    data['floors'] = data['floors'].astype(int)

    data['waterfront'] = data['waterfront'].astype( str )

    # Delete 'ID's duplicados
    data = data.drop_duplicates(subset=['id'], keep='last')
    # Removendo "Na"
    data = data.dropna(subset=['sqft_above'], axis=0)
    # Delete imóvel com 'bedrooms' == 33
    data.drop(data.loc[data['bedrooms'] == 33].index, inplace=True)

    return data

#=======================================
    # Feature Creation
def set_features( data ):
    data = data.copy()
    # Ano de construção:  > & < 1955
    data['constrution'] = data['yr_built'].apply(lambda x: '> 1955' if x > 1955
    else '< 1955')

    # Imóveis com ou sem porão
    data['basement'] = data['sqft_basement'].apply(lambda x: 'no' if x == 0
    else 'yes')

    # Colunas auxiliares pra def insights
    data['year'] = pd.to_datetime( data['date']).dt.year
    data['year'] = data['year'].astype(str)
    data['year_mouth'] = pd.to_datetime( data['date']).dt.strftime('%Y-%m')

    # Season
    data['month'] = pd.to_datetime( data['date']).dt.month
    data['season'] = data['month'].apply(lambda x: 'summer' if (x > 5) & (x < 8) else
                                                   'spring' if (x > 2) & (x < 5) else
                                                   'fall' if (x > 8) & (x < 12) else 'winter')

    # Waterfront
    data['waterfront_'] = data['waterfront'].apply(lambda x: 'sim' if x == '1' else 'não')

    # Imoveis com porão ou sem porão
    data['basement'] = data['sqft_basement'].apply(lambda x: 'no' if x == 0 else 'yes')

    # coluna condição  para adicionar no relatório
    data['describe_condition'] = data['condition'].apply(lambda x: 'too bad' if x == 1 else
                                                                       'bad' if x == 2 else
                                                                    'median' if x == 3 else
                                                                      'good' if x == 4 else 'excellent')

    return data

#=======================================
    # Imóveis sugeridos para compra
def overview_data( data, geofile ):
    st.sidebar.title(':house: House Rocket Analytics :house:')
    st.sidebar.subheader('https://github.com/Cassiano-Schmeiske')
    st.sidebar.write('Filtros para selecionar os imóveis sugeridos para compra e seu respectivo lucro na transação de venda.')
    st.title(':bar_chart: Imóveis recomendação - Compra:')
    st.write('Condições: \n- a) Imóveis abaixo do preço mediano da região \n- b) Imóveis em boas condições')

    # Agrupar os imóveis pelo (zipcode) e (mediana da região)
    df = data[['zipcode', 'price']].groupby('zipcode').median().reset_index()
    df = df.rename(columns={'price': 'price_median'})

    # merge
    data = pd.merge(df, data, on='zipcode', how='inner')

    # coluna "status" com a sugestão "buy" ou "no buy":
    for i in range(len(data)):
        if (data.loc[i, 'price'] < data.loc[i, 'price_median']) & (data.loc[i, 'condition'] >= 3):
            data.loc[i, 'status'] = 'buy'
        else:
            data.loc[i, 'status'] = 'no buy'

    # house selection
    buy_houses = data[data['status'] == 'buy'].sort_values( by=['describe_condition', 'price'] )

    f_condition = st.sidebar.multiselect('Enter Condition', buy_houses['describe_condition'].unique())
    f_zipcode = st.sidebar.multiselect('Enter Zipcode', buy_houses['zipcode'].unique())

    if (f_zipcode != []) & (f_condition != []):
        buy_houses = buy_houses.loc[(buy_houses['zipcode'].isin(f_zipcode)) & (buy_houses['describe_condition'].isin(f_condition)), :]
    elif (f_zipcode != []) & (f_condition == []):
        buy_houses = buy_houses.loc[data['zipcode'].isin(f_zipcode), :]
    elif (f_zipcode == []) & (f_condition != []):
        buy_houses = buy_houses.loc[buy_houses['describe_condition'].isin(f_condition), :]
    else:
        buy_houses = buy_houses.copy()

    st.dataframe(buy_houses[['id','zipcode', 'price', 'price_median', 'describe_condition']])
    st.sidebar.write( f'Foram selecionados {len(buy_houses)} imóveis dentro das condições acima, sugeridos para compra.')

#=======================================
    # Análise dos imóveis selecionados - Venda
    st.title(':chart_with_upwards_trend: Análise dos imóveis selecionados - Venda:')
    st.write('Condições: \n- a) Se o imóvel for comprado no preço acima da mediana por região + sazonalidade. \n' 
             ' A venda deve ser igual ao preço de compra + 10% ')
    st.write('- b) Se o imóvel for comprado no preço abaixo da mediana por região + sazonalidade. \n'
             'A venda deve ser igual ao preço de compra + 30%')

    # Agrupar os imóveis por região ( coluna zipcode ) e por sazonalidade (season)
    # Dentro de cada região / season encontrar a mediana do preço do imóvel.
    df2 = data[['zipcode', 'price', 'season']].groupby(['zipcode', 'season']).median().reset_index()
    df2 = df2.rename(columns={'price': 'price_median_season'})

    # merge
    buy_houses = pd.merge(buy_houses, df2, how='inner', on=['zipcode', 'season'])

    for i in range(len(buy_houses)):
        if buy_houses.loc[i, 'price'] <= buy_houses.loc[i, 'price_median_season']:
            buy_houses.loc[i, 'sale_price'] = buy_houses.loc[i, 'price'] * 1.30
        elif buy_houses.loc[i, 'price'] > buy_houses.loc[i, 'price_median_season']:
            buy_houses.loc[i, 'sale_price'] = buy_houses.loc[i, 'price'] * 1.10
        else:
            pass

    buy_houses['gain'] = buy_houses['sale_price'] - buy_houses['price']
    st.dataframe( buy_houses[['id', 'zipcode', 'price', 'season', 'price_median_season', 'describe_condition', 'sale_price', 'gain']], 1200, 450)
    st.sidebar.write( f'Lucro estimado com a venda dos imóveis: US$ {buy_houses["gain"].sum()}')

#=======================================
    # Maps
    st.title(':satellite: Visão geral dos imóveis selecionados')
    c1, c2 = st.beta_columns((1, 1))
    c1.header('Localização')

    # == Mapa de localização ==
    density_map = folium.Map(location=[buy_houses['lat'].mean(), buy_houses['long'].mean()], default_zoom_start=15)
    marker_cluster = MarkerCluster().add_to(density_map)

    for name, row in buy_houses.iterrows():
        folium.Marker([row['lat'], row['long']],
                      popup='Buy price U${0} Sell Price US$ {1} Gain US$ {2}. Features: {3} sqft, {4} bedrooms, {5} bathrooms, year built: {6}'.format(
                          row['price'],
                          row['sale_price'],
                          row['gain'],
                          row['sqft_living'],
                          row['bedrooms'],
                          row['bathrooms'],
                          row['yr_built'])).add_to(marker_cluster)

    with c1:
        folium_static(density_map)

    # == Mapa de densidade ==
    c2.header('Densidade de lucro')
    df4 = buy_houses[['gain', 'zipcode']].groupby('zipcode').mean().reset_index()
    df4.columns = ['ZIP', 'GAIN']
    geofile = geofile[geofile['ZIP'].isin(df4['ZIP'].tolist())]
    region_price_map = folium.Map(location=[buy_houses['lat'].mean(), buy_houses['long'].mean()], default_zoom_start=15)
    region_price_map.choropleth(data=df4,
                                geo_data=geofile,
                                columns=['ZIP', 'GAIN'],
                                key_on='feature.properties.ZIP',
                                fill_color='YlOrRd',
                                fill_opacity=0.7,
                                line_opacity=0.2,
                                legend_name='AVG GAIN')

    with c2:
        folium_static(region_price_map)

#=======================================
    # Statistic Descriptive
    if st.checkbox('Mostrar Statistic Descriptive'):
        num_attributes = data.select_dtypes(include=['int64', 'float64'])
        num_attributes = num_attributes.iloc[:, 1:]  # removendo colunas
        num_attributes = num_attributes.drop(columns=['price_median', 'id', 'lat', 'long', 'month'] )  # removendo colunas

        media = pd.DataFrame(num_attributes.apply(np.mean))
        mediana = pd.DataFrame(num_attributes.apply(np.median))
        std = pd.DataFrame(num_attributes.apply(np.std))

        max_ = pd.DataFrame(num_attributes.apply(np.max))
        min_ = pd.DataFrame(num_attributes.apply(np.min))

        # concatenar
        df1 = pd.concat([max_, min_, media, mediana, std], axis=1).reset_index()
        df1.columns = ['attributes', 'max', 'min', 'mean', 'median', 'std']

        st.dataframe(df1, 1000 , 1000)

#===========================================
def hypothesis( data ):
    # ==H1==
    st.title('Insights de negócio')
    c1, c2 = st.beta_columns(2)

    #H1
    c1.subheader('Hipótese 1: Imóveis com vista para a água são 30% em média mais caros')
    h1 = data[['price', 'waterfront_']].groupby('waterfront_').mean().reset_index()
    fig1 = px.bar(h1, x='waterfront_', y='price',
                  color='waterfront_',
                  labels={"waterfront_": "Visão para água","price": "Average price"},
                  template='simple_white')

    fig1.update_layout(showlegend=False)
    c1.plotly_chart(fig1, use_container_width=True)
    h1_percent = (h1.loc[1, 'price'] - h1.loc[0, 'price']) / h1.loc[0, 'price']
    c1.write(f'H1 é verdadeira, pois os imóveis com vista pra água são em média {h1_percent:.0%} mais caros')

    # ==H2==
    c2.subheader('Hipótese 2: Imóveis com data de construção menor que 1955 são 50% em média mais baratos')
    h2 = data[['price', 'constrution']].groupby('constrution').mean().reset_index()
    fig2 = px.bar(h2, x='constrution', y='price',
                  color='constrution',
                  labels={"constrution": "Ano da construção", "price": "Average price"},
                  template='simple_white')

    fig2.update_layout(showlegend=False)
    c2.plotly_chart(fig2, use_container_width=True)
    h2_percent = (h2.loc[1, 'price'] - h2.loc[0, 'price']) / h2.loc[1, 'price']
    c2.write(f'H2 é falsa, pois os imóveis construídos antes de 1955, são em média apenas {h2_percent:.0%} mais baratos' )

    c3, c4 = st.beta_columns(2)

    # ==H3==
    c3.subheader('Hipótese 3: Imóveis sem porão possuem sqrt_lot, são 50% maiores do que com porão')
    h3 = data[['sqft_lot', 'basement']].groupby('basement').mean().reset_index()
    fig3 = px.bar(h3, x='basement', y='sqft_lot',
                  color='basement',
                  labels={"basement": "Imóvel com porão", "sqft_lot": "Tamanho médio dos imóveis"},
                  template='simple_white')

    fig3.update_layout(showlegend=False)
    c3.plotly_chart(fig3, use_container_width=True)
    h3_percent = (h3.loc[0,'sqft_lot'] - h3.loc[1,'sqft_lot']) / h3.loc[1,'sqft_lot']
    c3.write( f'H3 é Falso, pois os imóveis sem porão, possuem sqrt_lot {h3_percent:.0%} maior do que imóveis com porão' )

    # ==H4==
    c4.subheader('Hipótese 4:  Houve crescimento do preço médio dos imóveis YoY ( Year over Year )')
    h4 = data[['price', 'year']].groupby('year').mean().reset_index()
    fig4 = px.bar(h4, x='year', y='price',
                  color='year',
                  labels={"year": "Ano", "price": "Preço médio"},
                  template='simple_white')

    fig4.update_layout(showlegend=False)
    c4.plotly_chart(fig4, use_container_width=True)
    h4_percent = (h4.loc[1, 'price'] - h4.loc[0, 'price']) / h4.loc[0, 'price']
    c4.write('H4 é falsa, pois o crescimento do preço entre os anos foi de {0:.2%}'.format(h4_percent))

    # ==H5==
    st.subheader('Hipótese 5:  Imóveis com 3 banheiros tem um crescimento MoM ( Month over Month ) de 15%')
    df5 = data[['price', 'bathrooms', 'date']].copy()
    # montar um df apenas com imóveis com 03 banheiros
    df5 = df5[df5['bathrooms'] == 3].reset_index(drop=True)
    # cria coluna mês do ano: YYYY-mm
    df5['month_yr'] = pd.to_datetime(df5['date']).dt.strftime('%Y-%m')
    # agrupar por data
    h5 = df5[['month_yr', 'price']].groupby('month_yr').mean().reset_index()

    # diferença entre os preço MoM
    h5['price_variation'] = h5['price'].diff() / 100
    h5['color'] = h5['price_variation'].apply(lambda x: 'negatigo' if x < 0 else 'positivo')

    fig5 = px.bar(h5, x='month_yr', y='price_variation',
                  color='color')

    fig5.update_layout(showlegend=False)
    st.plotly_chart(fig5, use_container_width=True)
    st.write('H5 é falsa, Não houve constância no rescimento dos Imóveis com 3 banheiros MoM ')



    return None

#===================================================
# MAIN FUNCTION
#===================================================

if __name__ == '__main__':
    #ETL

    #======Data Extration=====
    path = 'kc_house_data.csv'
    url = 'https://opendata.arcgis.com/datasets/83fc2e72903343aabff6de8cb445b81c_2.geojson'
    data = get_data( path )
    geofile = get_geofile( url )

    #========Transformation=======
    data = clean_data(data)
    data = set_features( data )
    overview_data( data, geofile)
    hypothesis( data )

